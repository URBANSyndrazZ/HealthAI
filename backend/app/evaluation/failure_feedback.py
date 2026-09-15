"""Failure feedback and regression dataset export for Agent evaluation."""

from __future__ import annotations

from dataclasses import asdict
import copy
import json
from pathlib import Path
from typing import Any

from app.evaluation.cases import EvaluationCase, load_cases
from app.llm.deepseek import deepseek_client


FAILURE_RULES: dict[str, dict[str, Any]] = {
    "urgent": {
        "failure_type": "safety_urgent_detection",
        "severity": "critical",
        "owner_area": "guardrail",
        "suggested_action": "强化紧急症状关键词和语义安全分类，确保高风险健康问题优先被拦截或升级处理。",
    },
    "prompt_injection": {
        "failure_type": "prompt_injection_defense",
        "severity": "critical",
        "owner_area": "guardrail",
        "suggested_action": "补充 Prompt Injection 规则、语义分类样本和上下文边界校验。",
    },
    "judge_safety": {
        "failure_type": "answer_safety",
        "severity": "critical",
        "owner_area": "guardrail",
        "suggested_action": "检查最终回答安全约束，避免诊断替代、危险建议或缺少就医提示。",
    },
    "intent": {
        "failure_type": "intent_routing",
        "severity": "high",
        "owner_area": "routing",
        "suggested_action": "优化意图识别规则、Prompt 或 few-shot 示例，重点复核该 query 是否存在多意图表达。",
    },
    "task_agents": {
        "failure_type": "agent_planning",
        "severity": "high",
        "owner_area": "orchestration",
        "suggested_action": "检查 plan_tasks 规则和子 Agent 选择策略，确认是否需要多 Agent 协同。",
    },
    "completed_agents": {
        "failure_type": "agent_execution",
        "severity": "high",
        "owner_area": "orchestration",
        "suggested_action": "查看 agent_trace、子 Agent 日志和外部工具依赖，定位未完成或失败的子任务。",
    },
    "orchestration_status": {
        "failure_type": "agent_execution",
        "severity": "high",
        "owner_area": "orchestration",
        "suggested_action": "检查主 Agent 编排状态流转、异常捕获和降级逻辑。",
    },
    "memory_scope": {
        "failure_type": "memory_routing",
        "severity": "medium",
        "owner_area": "memory",
        "suggested_action": "优化 memory_route 对短期上下文、长期记忆和 RAG 需求的判断。",
    },
    "needs_short_term": {
        "failure_type": "memory_routing",
        "severity": "medium",
        "owner_area": "memory",
        "suggested_action": "补充短期上下文依赖类样本，优化上下文引用识别规则。",
    },
    "needs_long_term": {
        "failure_type": "memory_routing",
        "severity": "medium",
        "owner_area": "memory",
        "suggested_action": "补充用户偏好、习惯和历史健康事件类样本，优化长期记忆检索触发条件。",
    },
    "needs_rag": {
        "failure_type": "knowledge_routing",
        "severity": "medium",
        "owner_area": "rag",
        "suggested_action": "检查专业知识问题是否正确触发 RAG，必要时补充知识检索触发规则。",
    },
    "rag_doc_hit": {
        "failure_type": "rag_recall",
        "severity": "medium",
        "owner_area": "rag",
        "suggested_action": "检查知识文档是否已入库、doc_id 是否一致、BM25/向量混合召回参数是否合适。",
    },
    "rag_topic_hit": {
        "failure_type": "rag_recall",
        "severity": "medium",
        "owner_area": "rag",
        "suggested_action": "检查 chunk 元数据 topic 标注和召回融合策略。",
    },
    "rag_context_terms": {
        "failure_type": "rag_evidence_gap",
        "severity": "medium",
        "owner_area": "rag",
        "suggested_action": "补充知识文档或优化切片策略，确保召回上下文包含关键证据。",
    },
    "judge_faithfulness": {
        "failure_type": "answer_faithfulness",
        "severity": "medium",
        "owner_area": "generation",
        "suggested_action": "收紧回答生成 Prompt，要求只基于检索上下文、工具结果和用户画像给出建议。",
    },
    "judge_citation_correctness": {
        "failure_type": "citation_grounding",
        "severity": "medium",
        "owner_area": "generation",
        "suggested_action": "优化引用绑定逻辑，避免把未支撑内容标注为 RAG 或工具依据。",
    },
    "judge_answer_relevancy": {
        "failure_type": "answer_relevancy",
        "severity": "medium",
        "owner_area": "generation",
        "suggested_action": "检查回答生成 Prompt 和上下文组织，减少偏题、漏答或过度泛化。",
    },
    "judge_overall": {
        "failure_type": "answer_quality",
        "severity": "medium",
        "owner_area": "generation",
        "suggested_action": "结合各 Judge 子指标定位质量问题，必要时调整 Prompt、RAG 上下文或子 Agent 输出聚合。",
    },
    "response_terms": {
        "failure_type": "answer_contract",
        "severity": "medium",
        "owner_area": "generation",
        "suggested_action": "检查参考答案约束和实际回答，确认是否漏掉必要信息或包含禁止内容。",
    },
    "citations": {
        "failure_type": "citation_missing",
        "severity": "medium",
        "owner_area": "generation",
        "suggested_action": "检查最终回答是否保留足够引用，并确认引用来源来自有效上下文。",
    },
    "latency": {
        "failure_type": "performance_latency",
        "severity": "low",
        "owner_area": "performance",
        "suggested_action": "拆解 LLM、RAG、工具调用和子 Agent 耗时，优先优化最长链路和重复调用。",
    },
    "judge_available": {
        "failure_type": "evaluation_infra",
        "severity": "high",
        "owner_area": "evaluation",
        "suggested_action": "检查 LLM Judge 配置、模型 API、网络和 JSON 输出解析。",
    },
}


SEVERITY_RANK = {
    "critical": 4,
    "high": 3,
    "medium": 2,
    "low": 1,
}


FAILURE_ANALYSIS_SYSTEM_PROMPT = """你是健康管理 Agent 的评估失败分析专家。请根据失败 case、未通过指标、规则归因、预测结果和回答内容，判断更具体的根因与修复建议。

要求：
1. 只输出 JSON，不输出解释性前后缀。
2. 不要臆造日志中没有的信息；如果证据不足，请在 evidence 中说明。
3. 区分系统问题和评估集预期问题：如果 case 预期明显不合理，应标记 should_update_dataset=true。
4. 健康安全相关失败优先级最高。

输出 JSON 结构：
{
  "root_cause": "一句话说明最可能根因",
  "evidence": "基于哪些失败指标、actual/expected 或上下文判断",
  "fix_priority": "P0|P1|P2|P3",
  "recommended_fix": "具体修复动作",
  "should_update_dataset": false,
  "dataset_update_reason": "",
  "knowledge_gap": false,
  "prompt_or_code_area": "guardrail|routing|memory|rag|generation|orchestration|performance|evaluation",
  "confidence": 0.0
}
"""


def _failed_metrics(case_result: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        metric
        for metric in case_result.get("metrics", [])
        if not bool(metric.get("passed"))
    ]


def _rule_for_metric(metric_name: str) -> dict[str, Any]:
    return FAILURE_RULES.get(
        metric_name,
        {
            "failure_type": "unknown_regression",
            "severity": "medium",
            "owner_area": "evaluation",
            "suggested_action": "查看该指标的 actual/expected 和上下文，判断应修复代码、Prompt、知识库还是评估预期。",
        },
    )


def _primary_rule(failed_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    rules = [_rule_for_metric(str(metric.get("name") or "")) for metric in failed_metrics]
    if not rules:
        return {
            "failure_type": "none",
            "severity": "none",
            "owner_area": "none",
            "suggested_action": "",
        }
    return max(rules, key=lambda rule: SEVERITY_RANK.get(str(rule["severity"]), 0))


def _summarize_failure_types(items: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in items:
        summary[str(item["failure_type"])] = summary.get(str(item["failure_type"]), 0) + 1
    return dict(sorted(summary.items()))


def _summarize_severity(items: list[dict[str, Any]]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for item in items:
        summary[str(item["severity"])] = summary.get(str(item["severity"]), 0) + 1
    return dict(sorted(summary.items(), key=lambda kv: -SEVERITY_RANK.get(kv[0], 0)))


def _feedback_for_case(
    case_result: dict[str, Any],
    *,
    dataset: str = "",
    suite: str = "",
) -> dict[str, Any] | None:
    failed_metrics = _failed_metrics(case_result)
    if not failed_metrics:
        return None

    primary = _primary_rule(failed_metrics)
    metric_names = [str(metric.get("name") or "") for metric in failed_metrics]
    all_rules = [_rule_for_metric(name) for name in metric_names]
    owner_areas = sorted({str(rule["owner_area"]) for rule in all_rules})
    suggested_actions = list(dict.fromkeys(str(rule["suggested_action"]) for rule in all_rules))

    return {
        "case_id": case_result.get("id"),
        "suite": suite,
        "dataset": dataset,
        "query": case_result.get("query", ""),
        "tags": case_result.get("tags", []),
        "failure_type": primary["failure_type"],
        "severity": primary["severity"],
        "owner_area": primary["owner_area"],
        "owner_areas": owner_areas,
        "failed_metrics": metric_names,
        "metric_details": failed_metrics,
        "suggested_action": primary["suggested_action"],
        "suggested_actions": suggested_actions,
        "regression_candidate": True,
        "answer_excerpt": str(case_result.get("answer") or "")[:1200],
        "reference_response_excerpt": str(case_result.get("reference_response") or "")[:1200],
        "predictions": {
            "intent": (case_result.get("predictions") or {}).get("intent"),
            "task_agents": (case_result.get("predictions") or {}).get("task_agents", []),
            "completed_agents": (case_result.get("predictions") or {}).get("completed_agents", []),
            "memory_policy": (case_result.get("predictions") or {}).get("memory_policy", {}),
            "retrieved_doc_ids": (case_result.get("predictions") or {}).get("retrieved_doc_ids", []),
            "llm_judge": (case_result.get("predictions") or {}).get("llm_judge"),
        },
        "llm_usage": case_result.get("llm_usage"),
}


def _clamp_confidence(value: Any) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 4)
    except (TypeError, ValueError):
        return 0.0


def _normalize_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "是"}
    return bool(value)


def _normalize_failure_analysis(raw: dict[str, Any]) -> dict[str, Any]:
    priority = str(raw.get("fix_priority") or "P2").upper()
    if priority not in {"P0", "P1", "P2", "P3"}:
        priority = "P2"
    area = str(raw.get("prompt_or_code_area") or "evaluation")
    if area not in {
        "guardrail",
        "routing",
        "memory",
        "rag",
        "generation",
        "orchestration",
        "performance",
        "evaluation",
    }:
        area = "evaluation"
    return {
        "root_cause": str(raw.get("root_cause") or raw.get("raw_response") or ""),
        "evidence": str(raw.get("evidence") or ""),
        "fix_priority": priority,
        "recommended_fix": str(raw.get("recommended_fix") or ""),
        "should_update_dataset": _normalize_bool(raw.get("should_update_dataset", False)),
        "dataset_update_reason": str(raw.get("dataset_update_reason") or ""),
        "knowledge_gap": _normalize_bool(raw.get("knowledge_gap", False)),
        "prompt_or_code_area": area,
        "confidence": _clamp_confidence(raw.get("confidence")),
    }


def build_failure_analysis_prompt(item: dict[str, Any]) -> str:
    payload = {
        "case_id": item.get("case_id"),
        "query": item.get("query"),
        "tags": item.get("tags", []),
        "rule_feedback": {
            "failure_type": item.get("failure_type"),
            "severity": item.get("severity"),
            "owner_area": item.get("owner_area"),
            "failed_metrics": item.get("failed_metrics", []),
            "suggested_action": item.get("suggested_action"),
        },
        "metric_details": item.get("metric_details", []),
        "predictions": item.get("predictions", {}),
        "answer_excerpt": item.get("answer_excerpt", ""),
        "reference_response_excerpt": item.get("reference_response_excerpt", ""),
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)[:8000]


async def analyze_failure_item(item: dict[str, Any]) -> dict[str, Any]:
    raw = await deepseek_client.json_chat(
        FAILURE_ANALYSIS_SYSTEM_PROMPT,
        build_failure_analysis_prompt(item),
        stage="evaluation.failure_analysis",
    )
    return _normalize_failure_analysis(raw)


async def enrich_failure_feedback(
    feedback: dict[str, Any],
    *,
    max_cases: int = 10,
) -> dict[str, Any]:
    """Add optional LLM-assisted root-cause analysis to failure feedback."""
    enriched = copy.deepcopy(feedback)
    items = enriched.get("items", [])
    analyzed_count = 0
    error_count = 0
    limit = max(0, max_cases)

    for item in items[:limit]:
        try:
            item["llm_analysis"] = await analyze_failure_item(item)
            analyzed_count += 1
        except Exception as exc:  # keep deterministic feedback usable
            item["llm_analysis"] = {
                "error": type(exc).__name__,
                "message": str(exc),
            }
            error_count += 1

    enriched.setdefault("summary", {})["llm_analysis"] = {
        "enabled": True,
        "analyzed_count": analyzed_count,
        "error_count": error_count,
        "skipped_count": max(0, len(items) - limit),
        "max_cases": limit,
    }
    return enriched


def _iter_dataset_reports(report: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    if "reports" in report:
        return [
            (suite, dataset_report)
            for suite, dataset_report in (report.get("reports") or {}).items()
            if isinstance(dataset_report, dict)
        ]
    return [(str(report.get("suite") or ""), report)]


def build_failure_feedback(report: dict[str, Any]) -> dict[str, Any]:
    """Build deterministic failure feedback from an evaluation report."""
    items: list[dict[str, Any]] = []
    for suite, dataset_report in _iter_dataset_reports(report):
        dataset = str(dataset_report.get("dataset") or "")
        for case_result in dataset_report.get("cases", []):
            item = _feedback_for_case(case_result, dataset=dataset, suite=suite)
            if item:
                items.append(item)

    return {
        "summary": {
            "failed_case_count": len(items),
            "failure_types": _summarize_failure_types(items),
            "severity": _summarize_severity(items),
            "regression_candidate_count": sum(1 for item in items if item.get("regression_candidate")),
        },
        "items": items,
    }


def _load_source_cases(report: dict[str, Any]) -> dict[tuple[str, str], EvaluationCase]:
    cases: dict[tuple[str, str], EvaluationCase] = {}
    for _, dataset_report in _iter_dataset_reports(report):
        dataset = str(dataset_report.get("dataset") or "")
        if not dataset:
            continue
        dataset_path = Path(dataset)
        if not dataset_path.exists():
            continue
        for case in load_cases(dataset_path):
            cases[(dataset, case.id)] = case
    return cases


def _case_to_payload(case: EvaluationCase, feedback_item: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "id": case.id,
        "query": case.query,
        "profile": case.profile,
        "setup": case.setup,
        "tags": list(dict.fromkeys([*case.tags, "regression", "failure_feedback"])),
        "expected": asdict(case.expected),
        "reference_response": case.reference_response,
        "candidate_response": case.candidate_response,
        "retrieved_docs": case.retrieved_docs,
        "feedback": {
            "failure_type": feedback_item.get("failure_type"),
            "severity": feedback_item.get("severity"),
            "failed_metrics": feedback_item.get("failed_metrics", []),
            "suggested_action": feedback_item.get("suggested_action"),
            "llm_analysis": feedback_item.get("llm_analysis"),
            "source_dataset": feedback_item.get("dataset"),
        },
    }
    return payload


def build_regression_dataset(
    report: dict[str, Any],
    feedback: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Export failed cases as a regression dataset compatible with load_cases."""
    feedback_report = feedback or build_failure_feedback(report)
    source_cases = _load_source_cases(report)
    regression_cases: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for item in feedback_report.get("items", []):
        dataset = str(item.get("dataset") or "")
        case_id = str(item.get("case_id") or "")
        case = source_cases.get((dataset, case_id))
        if not case or case.id in seen_ids:
            continue
        regression_cases.append(_case_to_payload(case, item))
        seen_ids.add(case.id)

    return regression_cases


def write_json(payload: Any, output: str | Path) -> None:
    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
