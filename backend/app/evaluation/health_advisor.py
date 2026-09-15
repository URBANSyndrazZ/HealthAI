"""Deterministic Health Advisor evaluation runner."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path
from typing import Any

from app.agents.health_advisor.nodes.check_safety import _check_urgent_keywords
from app.agents.health_advisor.nodes.memory_route import memory_route
from app.agents.health_advisor.nodes.plan_tasks import plan_tasks
from app.agents.health_advisor.state import HealthAdvisorState
from app.core.observability import configure_logging
from app.core.prompt_security import assess_prompt_injection
from app.memory.long_term import long_term_memory
from app.evaluation.cases import EvaluationCase, load_cases
from app.evaluation.metrics import (
    MetricResult,
    agent_set_metric,
    aggregate_results,
    exact_match_metric,
    metric_to_dict,
    named_set_metric,
    optional_exact_match_metric,
    optional_max_latency_metric,
    optional_min_count_metric,
    rag_context_terms_metric,
    rag_doc_hit_metric,
    rag_topic_hit_metric,
    response_terms_metric,
    score_threshold_metric,
)
from app.evaluation.e2e_agent import run_health_advisor_replay
from app.evaluation.failure_feedback import (
    build_failure_feedback,
    build_regression_dataset,
    enrich_failure_feedback,
    write_json,
)
from app.evaluation.live_rag import retrieve_live_rag
from app.evaluation.llm_judge import judge_answer, judge_metrics
from app.evaluation.ragas_adapter import run_ragas_evaluation
from app.llm.usage import aggregate_usage_summaries, track_llm_usage
from app.rag.retriever import rag_retriever


logger = logging.getLogger(__name__)

DEFAULT_DATASET = Path(__file__).with_name("datasets") / "health_advisor_cases.json"
DATASET_DIR = Path(__file__).with_name("datasets")
SUITE_DATASETS = {
    "health_advisor": DEFAULT_DATASET,
    "safety": DATASET_DIR / "safety_cases.json",
    "routing": DATASET_DIR / "routing_cases.json",
    "memory": DATASET_DIR / "memory_cases.json",
    "rag": DATASET_DIR / "rag_cases.json",
    "e2e_agent": DATASET_DIR / "e2e_agent_cases.json",
}


INTENT_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("urgent_concern", ("胸痛", "呼吸困难", "昏迷", "晕倒", "大出血", "自杀", "急救")),
    ("nutrition", ("吃", "饮食", "营养", "热量", "蛋白质", "早餐", "午餐", "晚餐")),
    ("exercise", ("运动", "锻炼", "训练", "跑步", "健身", "减脂", "增肌", "身体活动", "活动量")),
    ("environment", ("天气", "空气", "雾霾", "pm2.5", "aqi", "户外", "紫外线")),
    ("symptom_check", ("头疼", "发烧", "咳嗽", "疼", "不舒服", "症状")),
    ("lifestyle", ("睡眠", "睡不好", "睡多久", "睡", "失眠", "作息", "熬夜", "压力", "习惯")),
)


def heuristic_intent(query: str) -> str:
    """Classify intent without calling an LLM, for CI-safe offline evaluation."""
    lowered = query.lower()
    for intent, keywords in INTENT_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            return intent
    return "general_health"


def _metric_names_for_case(case: EvaluationCase, metrics: list[MetricResult]) -> dict[str, float]:
    return {metric.name: metric.score for metric in metrics}


async def evaluate_case(
    case: EvaluationCase,
    *,
    live_rag: bool = False,
    llm_judge: bool = False,
    judge_threshold: float = 0.8,
    e2e_agent: bool = False,
) -> dict[str, Any]:
    """Evaluate one case with deterministic checks."""
    logger.info(
        "[evaluation] case start id=%s live_rag=%s llm_judge=%s e2e_agent=%s",
        case.id,
        live_rag,
        llm_judge,
        e2e_agent,
    )
    answer = case.candidate_response or case.reference_response
    retrieved_docs = case.retrieved_docs
    live_rag_report: dict[str, Any] | None = None
    e2e_report: dict[str, Any] | None = None
    tool_context_docs: list[dict[str, Any]] = []

    if e2e_agent:
        e2e_report = await run_health_advisor_replay(case)
        answer = e2e_report.get("response", "")
        retrieved_docs = e2e_report.get("retrieved_docs", [])
        predicted_intent = e2e_report.get("intent") or heuristic_intent(case.query)
        safety_flag = e2e_report.get("safety_flag") or {}
        is_urgent = bool(safety_flag.get("is_urgent", False))
        urgent_reason = str(safety_flag.get("reason") or "")
        prompt_security_dict = e2e_report.get("prompt_security") or {}
        prompt_injection = bool(prompt_security_dict.get("is_suspicious", False))
        memory_policy = e2e_report.get("memory_policy") or {}
        predicted_agents = list(e2e_report.get("task_agents", []))
        completed_agents = list(e2e_report.get("completed_agents", []))
        orchestration_status = e2e_report.get("orchestration_status")
        citations = list(e2e_report.get("citations", []))
        elapsed_ms = e2e_report.get("elapsed_ms")
        tool_context_docs = list(e2e_report.get("tool_context_docs", []))
    else:
        predicted_intent = heuristic_intent(case.query)
        is_urgent, urgent_reason = _check_urgent_keywords(case.query)
        prompt_security = assess_prompt_injection(case.query)
        prompt_security_dict = prompt_security.model_dump()
        prompt_injection = prompt_security.is_suspicious

        if live_rag:
            retrieved_docs, live_rag_report = await retrieve_live_rag(case.query)
            if live_rag_report and live_rag_report.get("error"):
                logger.warning(
                    "[evaluation] live RAG failed case=%s error=%s message=%s",
                    case.id,
                    live_rag_report.get("error"),
                    live_rag_report.get("message"),
                )
            else:
                logger.info(
                    "[evaluation] live RAG finished case=%s docs=%d elapsed_ms=%s",
                    case.id,
                    len(retrieved_docs),
                    (live_rag_report or {}).get("elapsed_ms"),
                )

        state = HealthAdvisorState(
            user_id="eval_user",
            session_id=case.id,
            user_message=case.query,
            context={
                "profile": case.profile,
                "short_term_history": case.setup.get("short_term_history", []),
                "long_term_memories": case.setup.get("long_term_memories", []),
            },
        )
        state["intent"] = predicted_intent
        state = await memory_route(state)
        memory_policy = state.get("memory_policy") or {}
        state = await plan_tasks(state)
        predicted_agents = [
            task.get("agent_name", "")
            for task in state.get("sub_tasks", [])
            if task.get("agent_name")
        ]
        completed_agents = []
        orchestration_status = state.get("orchestration_status")
        citations = []
        elapsed_ms = (live_rag_report or {}).get("elapsed_ms")

    should_score_rag = bool(retrieved_docs or live_rag or e2e_agent)
    metrics = [
        exact_match_metric("intent", predicted_intent, case.expected.intent),
        exact_match_metric("urgent", is_urgent, case.expected.urgent),
        exact_match_metric(
            "prompt_injection",
            prompt_injection,
            case.expected.prompt_injection,
        ),
        agent_set_metric(predicted_agents, case.expected.task_agents),
        response_terms_metric(answer, case.expected.required_terms, case.expected.forbidden_terms),
    ]
    optional_metrics = [
        optional_exact_match_metric("memory_scope", memory_policy.get("scope"), case.expected.memory_scope),
        optional_exact_match_metric(
            "needs_short_term",
            memory_policy.get("needs_short_term"),
            case.expected.needs_short_term,
        ),
        optional_exact_match_metric(
            "needs_long_term",
            memory_policy.get("needs_long_term"),
            case.expected.needs_long_term,
        ),
        optional_exact_match_metric("needs_rag", memory_policy.get("needs_rag"), case.expected.needs_rag),
        rag_doc_hit_metric(retrieved_docs, case.expected.rag_doc_ids)
        if should_score_rag
        else None,
        rag_topic_hit_metric(retrieved_docs, case.expected.rag_topics)
        if should_score_rag
        else None,
        rag_context_terms_metric(retrieved_docs, case.expected.rag_context_terms)
        if should_score_rag
        else None,
        named_set_metric("completed_agents", completed_agents, case.expected.completed_agents)
        if e2e_agent and case.expected.completed_agents
        else None,
        optional_exact_match_metric(
            "orchestration_status",
            orchestration_status,
            case.expected.orchestration_status,
        )
        if e2e_agent
        else None,
        optional_min_count_metric("citations", len(citations), case.expected.min_citations)
        if e2e_agent
        else None,
        optional_max_latency_metric(elapsed_ms, case.expected.max_latency_ms)
        if e2e_agent
        else None,
    ]
    metrics.extend(metric for metric in optional_metrics if metric is not None)
    llm_judge_report: dict[str, Any] | None = None
    if llm_judge and answer:
        try:
            judge_context_docs = [*retrieved_docs, *tool_context_docs]
            logger.info("[evaluation] LLM judge start case=%s", case.id)
            llm_judge_report = await judge_answer(
                query=case.query,
                answer=answer,
                reference_response=case.reference_response,
                retrieved_docs=judge_context_docs,
            )
            judge_metric_keys = (
                ("answer_relevancy", "faithfulness", "safety", "citation_correctness", "overall")
                if judge_context_docs
                else ("answer_relevancy", "faithfulness", "safety", "overall")
            )
            metrics.extend(
                judge_metrics(
                    llm_judge_report,
                    threshold=judge_threshold,
                    metric_keys=judge_metric_keys,
                )
            )
            logger.info(
                "[evaluation] LLM judge finished case=%s overall=%s",
                case.id,
                llm_judge_report.get("overall"),
            )
        except Exception as exc:
            llm_judge_report = {
                "error": type(exc).__name__,
                "message": str(exc),
            }
            metrics.append(
                score_threshold_metric(
                    "judge_available",
                    0.0,
                    threshold=1.0,
                    details=llm_judge_report,
                )
            )
            logger.exception("[evaluation] LLM judge failed case=%s", case.id)
    elif llm_judge:
        llm_judge_report = {"skipped": True, "reason": "Case has no answer text to judge."}
        logger.info("[evaluation] LLM judge skipped case=%s reason=no_answer", case.id)

    result = {
        "id": case.id,
        "tags": case.tags,
        "query": case.query,
        "answer": answer,
        "reference_response": case.reference_response,
        "retrieved_docs": retrieved_docs,
        "predictions": {
            "intent": predicted_intent,
            "urgent": is_urgent,
            "urgent_reason": urgent_reason,
            "prompt_security": prompt_security_dict,
            "memory_policy": memory_policy,
            "task_agents": predicted_agents,
            "completed_agents": completed_agents,
            "orchestration_status": orchestration_status,
            "retrieved_doc_ids": [doc.get("id") for doc in retrieved_docs],
            "retrieved_topics": [
                (doc.get("metadata") or {}).get("topic") or doc.get("topic")
                for doc in retrieved_docs
            ],
            "live_rag": live_rag_report,
            "llm_judge": llm_judge_report,
            "e2e_agent": e2e_report,
            "tool_context_doc_ids": [doc.get("id") for doc in tool_context_docs],
        },
        "metric_scores": _metric_names_for_case(case, metrics),
        "metrics": [metric_to_dict(metric) for metric in metrics],
    }
    logger.info(
        "[evaluation] case finished id=%s failed_metrics=%s",
        case.id,
        [metric.name for metric in metrics if not metric.passed],
    )
    return result


async def run_evaluation(
    dataset: str | Path = DEFAULT_DATASET,
    min_score: float = 0.85,
    live_rag: bool = False,
    llm_judge: bool = False,
    judge_threshold: float = 0.8,
    ragas: bool = False,
    e2e_agent: bool = False,
    llm_failure_analysis: bool = False,
    failure_analysis_limit: int = 10,
) -> dict[str, Any]:
    cases = load_cases(dataset)
    logger.info(
        "[evaluation] dataset start path=%s cases=%d live_rag=%s llm_judge=%s ragas=%s e2e_agent=%s",
        dataset,
        len(cases),
        live_rag,
        llm_judge,
        ragas,
        e2e_agent,
    )
    case_results = []
    for case in cases:
        with track_llm_usage() as usage_tracker:
            case_result = await evaluate_case(
                case,
                live_rag=live_rag,
                llm_judge=llm_judge,
                judge_threshold=judge_threshold,
                e2e_agent=e2e_agent,
            )
        case_result["llm_usage"] = usage_tracker.summary(include_calls=True)
        case_results.append(case_result)

    summary = aggregate_results(case_results)
    summary["passed"] = summary["overall_score"] >= min_score and not summary["failed_cases"]
    summary["min_score"] = min_score
    summary["llm_usage"] = aggregate_usage_summaries(
        [case_result.get("llm_usage") for case_result in case_results]
    )
    report = {
        "dataset": str(dataset),
        "options": {
            "live_rag": live_rag,
            "llm_judge": llm_judge,
            "judge_threshold": judge_threshold,
            "ragas": ragas,
            "e2e_agent": e2e_agent,
            "llm_failure_analysis": llm_failure_analysis,
            "failure_analysis_limit": failure_analysis_limit,
        },
        "summary": summary,
        "llm_usage": summary["llm_usage"],
        "cases": case_results,
    }
    report["failure_feedback"] = build_failure_feedback(report)
    if llm_failure_analysis:
        with track_llm_usage() as usage_tracker:
            report["failure_feedback"] = await enrich_failure_feedback(
                report["failure_feedback"],
                max_cases=failure_analysis_limit,
            )
        analysis_usage = usage_tracker.summary(include_calls=True)
        report["failure_feedback"]["llm_analysis_usage"] = analysis_usage
        report["llm_usage"] = aggregate_usage_summaries([report["llm_usage"], analysis_usage])
        report["summary"]["llm_usage"] = report["llm_usage"]
    if ragas:
        logger.info("[evaluation] Ragas start dataset=%s", dataset)
        report["ragas"] = run_ragas_evaluation(case_results)
        logger.info("[evaluation] Ragas finished dataset=%s skipped=%s", dataset, report["ragas"].get("skipped"))
    logger.info(
        "[evaluation] dataset finished path=%s overall_score=%s passed=%s",
        dataset,
        summary["overall_score"],
        summary["passed"],
    )
    return report


async def run_evaluation_suite(
    suite: str = "health_advisor",
    min_score: float = 0.85,
    live_rag: bool = False,
    llm_judge: bool = False,
    judge_threshold: float = 0.8,
    ragas: bool = False,
    e2e_agent: bool = False,
    llm_failure_analysis: bool = False,
    failure_analysis_limit: int = 10,
) -> dict[str, Any]:
    """Run one named suite or every built-in suite."""
    logger.info("[evaluation] suite start suite=%s", suite)
    if suite == "all":
        reports = {
            name: await run_evaluation(
                dataset,
                min_score=min_score,
                live_rag=live_rag,
                llm_judge=llm_judge,
                judge_threshold=judge_threshold,
                ragas=ragas,
                e2e_agent=e2e_agent,
                llm_failure_analysis=False,
                failure_analysis_limit=failure_analysis_limit,
            )
            for name, dataset in SUITE_DATASETS.items()
        }
        suite_scores = {
            name: report["summary"]["overall_score"]
            for name, report in reports.items()
        }
        passed = all(report["summary"]["passed"] for report in reports.values())
        overall = round(sum(suite_scores.values()) / len(suite_scores), 4) if suite_scores else 0.0
        llm_usage = aggregate_usage_summaries(
            [report.get("llm_usage") for report in reports.values()]
        )
        result = {
            "suite": "all",
            "summary": {
                "overall_score": overall,
                "suite_scores": suite_scores,
                "passed": passed,
                "min_score": min_score,
                "llm_usage": llm_usage,
            },
            "llm_usage": llm_usage,
            "reports": reports,
        }
        result["failure_feedback"] = build_failure_feedback(result)
        if llm_failure_analysis:
            with track_llm_usage() as usage_tracker:
                result["failure_feedback"] = await enrich_failure_feedback(
                    result["failure_feedback"],
                    max_cases=failure_analysis_limit,
                )
            analysis_usage = usage_tracker.summary(include_calls=True)
            result["failure_feedback"]["llm_analysis_usage"] = analysis_usage
            result["llm_usage"] = aggregate_usage_summaries([result["llm_usage"], analysis_usage])
            result["summary"]["llm_usage"] = result["llm_usage"]
        logger.info("[evaluation] suite finished suite=all overall_score=%s passed=%s", overall, passed)
        return result

    if suite not in SUITE_DATASETS:
        valid = ", ".join(["all", *SUITE_DATASETS.keys()])
        raise ValueError(f"Unknown evaluation suite: {suite}. Valid values: {valid}")

    report = await run_evaluation(
        SUITE_DATASETS[suite],
        min_score=min_score,
        live_rag=live_rag,
        llm_judge=llm_judge,
        judge_threshold=judge_threshold,
        ragas=ragas,
        e2e_agent=e2e_agent,
        llm_failure_analysis=False,
        failure_analysis_limit=failure_analysis_limit,
    )
    report["suite"] = suite
    report["failure_feedback"] = build_failure_feedback(report)
    report["options"]["llm_failure_analysis"] = llm_failure_analysis
    report["options"]["failure_analysis_limit"] = failure_analysis_limit
    if llm_failure_analysis:
        with track_llm_usage() as usage_tracker:
            report["failure_feedback"] = await enrich_failure_feedback(
                report["failure_feedback"],
                max_cases=failure_analysis_limit,
            )
        analysis_usage = usage_tracker.summary(include_calls=True)
        report["failure_feedback"]["llm_analysis_usage"] = analysis_usage
        report["llm_usage"] = aggregate_usage_summaries([report["llm_usage"], analysis_usage])
        report["summary"]["llm_usage"] = report["llm_usage"]
    logger.info(
        "[evaluation] suite finished suite=%s overall_score=%s passed=%s",
        suite,
        report["summary"]["overall_score"],
        report["summary"]["passed"],
    )
    return report


def _write_report(report: dict[str, Any], output: str | None) -> None:
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if output:
        output_path = Path(output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)


async def _run_from_args(args: argparse.Namespace) -> dict[str, Any]:
    try:
        if args.suite:
            return await run_evaluation_suite(
                args.suite,
                min_score=args.min_score,
                live_rag=args.live_rag,
                llm_judge=args.llm_judge,
                judge_threshold=args.judge_threshold,
                ragas=args.ragas,
                e2e_agent=args.e2e_agent,
                llm_failure_analysis=args.llm_failure_analysis,
                failure_analysis_limit=args.failure_analysis_limit,
            )
        return await run_evaluation(
            args.dataset,
            min_score=args.min_score,
            live_rag=args.live_rag,
            llm_judge=args.llm_judge,
            judge_threshold=args.judge_threshold,
            ragas=args.ragas,
            e2e_agent=args.e2e_agent,
            llm_failure_analysis=args.llm_failure_analysis,
            failure_analysis_limit=args.failure_analysis_limit,
        )
    finally:
        await rag_retriever.close()
        await long_term_memory.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Health Advisor evaluation")
    parser.add_argument("--dataset", default=str(DEFAULT_DATASET), help="Path to evaluation dataset JSON")
    parser.add_argument(
        "--suite",
        choices=["all", *SUITE_DATASETS.keys()],
        help="Run a built-in evaluation suite. Overrides --dataset when set.",
    )
    parser.add_argument("--output", help="Optional path to write JSON report")
    parser.add_argument("--min-score", type=float, default=0.85, help="Minimum aggregate score")
    parser.add_argument("--live-rag", action="store_true", help="Retrieve documents from live Elasticsearch RAG")
    parser.add_argument("--llm-judge", action="store_true", help="Use LLM-as-judge for answer quality metrics")
    parser.add_argument("--judge-threshold", type=float, default=0.8, help="Minimum score for LLM judge metrics")
    parser.add_argument("--ragas", action="store_true", help="Run optional Ragas metrics when dependencies are installed")
    parser.add_argument("--e2e-agent", action="store_true", help="Replay cases through the full HealthAdvisorAgent graph")
    parser.add_argument("--export-failures", help="Optional path to write deterministic failure feedback JSON")
    parser.add_argument(
        "--export-regression-dataset",
        help="Optional path to write failed cases as a regression dataset JSON",
    )
    parser.add_argument(
        "--llm-failure-analysis",
        action="store_true",
        help="Use LLM to add root-cause analysis for failed cases",
    )
    parser.add_argument(
        "--failure-analysis-limit",
        type=int,
        default=10,
        help="Maximum failed cases to analyze with LLM",
    )
    parser.add_argument("--log-level", default="INFO", help="CLI log level, e.g. INFO, WARNING, DEBUG")
    args = parser.parse_args()
    log_level = getattr(logging, args.log_level.upper(), logging.INFO)
    configure_logging(log_level)

    report = asyncio.run(_run_from_args(args))
    _write_report(report, args.output)
    if args.export_failures:
        write_json(report.get("failure_feedback") or build_failure_feedback(report), args.export_failures)
    if args.export_regression_dataset:
        write_json(
            build_regression_dataset(report, report.get("failure_feedback")),
            args.export_regression_dataset,
        )
    if not report["summary"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
