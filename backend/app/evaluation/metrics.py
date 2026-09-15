"""Metrics for deterministic Agent evaluation."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MetricResult:
    name: str
    score: float
    passed: bool
    details: dict[str, Any] = field(default_factory=dict)


def exact_match_metric(name: str, actual: Any, expected: Any) -> MetricResult:
    passed = actual == expected
    return MetricResult(
        name=name,
        score=1.0 if passed else 0.0,
        passed=passed,
        details={"actual": actual, "expected": expected},
    )


def agent_set_metric(actual: list[str], expected: list[str]) -> MetricResult:
    return named_set_metric("task_agents", actual, expected)


def named_set_metric(name: str, actual: list[str], expected: list[str]) -> MetricResult:
    actual_set = set(actual)
    expected_set = set(expected)
    if not expected_set and not actual_set:
        score = 1.0
    elif not expected_set:
        score = 0.0
    else:
        score = len(actual_set & expected_set) / len(expected_set | actual_set)
    return MetricResult(
        name=name,
        score=round(score, 4),
        passed=score == 1.0,
        details={"actual": sorted(actual_set), "expected": sorted(expected_set)},
    )


def response_terms_metric(response: str, required: list[str], forbidden: list[str]) -> MetricResult:
    required_hits = [term for term in required if term in response]
    forbidden_hits = [term for term in forbidden if term in response]
    total = len(required) + len(forbidden)
    if total == 0:
        return MetricResult(name="response_terms", score=1.0, passed=True)

    misses = len(required) - len(required_hits)
    violations = len(forbidden_hits)
    score = max(0.0, (total - misses - violations) / total)
    return MetricResult(
        name="response_terms",
        score=round(score, 4),
        passed=misses == 0 and violations == 0,
        details={
            "required_hits": required_hits,
            "required_missing": [term for term in required if term not in required_hits],
            "forbidden_hits": forbidden_hits,
        },
    )


def optional_exact_match_metric(name: str, actual: Any, expected: Any) -> MetricResult | None:
    if expected is None:
        return None
    return exact_match_metric(name, actual, expected)


def optional_min_count_metric(name: str, actual_count: int, expected_min: int | None) -> MetricResult | None:
    if expected_min is None:
        return None
    passed = actual_count >= expected_min
    score = 1.0 if passed else (actual_count / expected_min if expected_min else 1.0)
    return MetricResult(
        name=name,
        score=round(score, 4),
        passed=passed,
        details={"actual": actual_count, "expected_min": expected_min},
    )


def optional_max_latency_metric(elapsed_ms: float | None, max_latency_ms: int | None) -> MetricResult | None:
    if max_latency_ms is None:
        return None
    elapsed = float(elapsed_ms or 0.0)
    passed = elapsed <= max_latency_ms
    score = 1.0 if passed else max(0.0, max_latency_ms / elapsed if elapsed else 0.0)
    return MetricResult(
        name="latency",
        score=round(score, 4),
        passed=passed,
        details={"actual_ms": elapsed, "expected_max_ms": max_latency_ms},
    )


def score_threshold_metric(
    name: str,
    score: float | int | None,
    threshold: float = 0.8,
    details: dict[str, Any] | None = None,
) -> MetricResult:
    normalized_score = max(0.0, min(1.0, float(score or 0.0)))
    return MetricResult(
        name=name,
        score=round(normalized_score, 4),
        passed=normalized_score >= threshold,
        details={"threshold": threshold, **(details or {})},
    )


def rag_doc_hit_metric(docs: list[dict[str, Any]], expected_ids: list[str]) -> MetricResult | None:
    if not expected_ids:
        return None
    actual_ids = {str(doc.get("id") or "") for doc in docs}
    expected_set = set(expected_ids)
    hits = sorted(actual_ids & expected_set)
    score = len(hits) / len(expected_set) if expected_set else 1.0
    return MetricResult(
        name="rag_doc_hit",
        score=round(score, 4),
        passed=score == 1.0,
        details={"actual": sorted(actual_ids), "expected": sorted(expected_set), "hits": hits},
    )


def rag_topic_hit_metric(docs: list[dict[str, Any]], expected_topics: list[str]) -> MetricResult | None:
    if not expected_topics:
        return None
    actual_topics = {
        str((doc.get("metadata") or {}).get("topic") or doc.get("topic") or "")
        for doc in docs
    }
    expected_set = set(expected_topics)
    hits = sorted(actual_topics & expected_set)
    score = len(hits) / len(expected_set) if expected_set else 1.0
    return MetricResult(
        name="rag_topic_hit",
        score=round(score, 4),
        passed=score == 1.0,
        details={"actual": sorted(actual_topics), "expected": sorted(expected_set), "hits": hits},
    )


def rag_context_terms_metric(docs: list[dict[str, Any]], required_terms: list[str]) -> MetricResult | None:
    if not required_terms:
        return None
    context = "\n".join(str(doc.get("content") or "") for doc in docs)
    hits = [term for term in required_terms if term in context]
    score = len(hits) / len(required_terms) if required_terms else 1.0
    return MetricResult(
        name="rag_context_terms",
        score=round(score, 4),
        passed=score == 1.0,
        details={
            "required_hits": hits,
            "required_missing": [term for term in required_terms if term not in hits],
        },
    )


def aggregate_results(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate metric scores across cases."""
    metric_scores: dict[str, list[float]] = {}
    for case in case_results:
        for metric in case["metrics"]:
            metric_scores.setdefault(metric["name"], []).append(float(metric["score"]))

    metrics = {
        name: round(sum(scores) / len(scores), 4)
        for name, scores in sorted(metric_scores.items())
        if scores
    }
    overall = round(sum(metrics.values()) / len(metrics), 4) if metrics else 0.0
    return {
        "overall_score": overall,
        "metrics": metrics,
        "case_count": len(case_results),
        "failed_cases": [
            case["id"]
            for case in case_results
            if any(not metric["passed"] for metric in case["metrics"])
        ],
    }


def metric_to_dict(metric: MetricResult) -> dict[str, Any]:
    return {
        "name": metric.name,
        "score": metric.score,
        "passed": metric.passed,
        "details": metric.details,
    }
