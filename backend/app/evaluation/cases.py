"""Evaluation case schema and loader."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ExpectedOutcome:
    intent: str = "general_health"
    urgent: bool = False
    prompt_injection: bool = False
    task_agents: list[str] = field(default_factory=list)
    required_terms: list[str] = field(default_factory=list)
    forbidden_terms: list[str] = field(default_factory=list)
    memory_scope: str | None = None
    needs_short_term: bool | None = None
    needs_long_term: bool | None = None
    needs_rag: bool | None = None
    rag_doc_ids: list[str] = field(default_factory=list)
    rag_topics: list[str] = field(default_factory=list)
    rag_context_terms: list[str] = field(default_factory=list)
    completed_agents: list[str] = field(default_factory=list)
    orchestration_status: str | None = None
    min_citations: int | None = None
    max_latency_ms: int | None = None


@dataclass(frozen=True)
class EvaluationCase:
    id: str
    query: str
    expected: ExpectedOutcome
    profile: dict[str, Any] = field(default_factory=dict)
    setup: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)
    reference_response: str = ""
    candidate_response: str = ""
    retrieved_docs: list[dict[str, Any]] = field(default_factory=list)


def _expected_from_dict(payload: dict[str, Any]) -> ExpectedOutcome:
    return ExpectedOutcome(
        intent=payload.get("intent", "general_health"),
        urgent=bool(payload.get("urgent", False)),
        prompt_injection=bool(payload.get("prompt_injection", False)),
        task_agents=list(payload.get("task_agents", [])),
        required_terms=list(payload.get("required_terms", [])),
        forbidden_terms=list(payload.get("forbidden_terms", [])),
        memory_scope=payload.get("memory_scope"),
        needs_short_term=payload.get("needs_short_term"),
        needs_long_term=payload.get("needs_long_term"),
        needs_rag=payload.get("needs_rag"),
        rag_doc_ids=list(payload.get("rag_doc_ids", [])),
        rag_topics=list(payload.get("rag_topics", [])),
        rag_context_terms=list(payload.get("rag_context_terms", [])),
        completed_agents=list(payload.get("completed_agents", [])),
        orchestration_status=payload.get("orchestration_status"),
        min_citations=payload.get("min_citations"),
        max_latency_ms=payload.get("max_latency_ms"),
    )


def load_cases(path: str | Path) -> list[EvaluationCase]:
    """Load evaluation cases from a JSON file."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("Evaluation dataset must be a JSON array")

    cases: list[EvaluationCase] = []
    for index, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Case {index} must be an object")
        expected = _expected_from_dict(item.get("expected", {}))
        cases.append(
            EvaluationCase(
                id=str(item.get("id") or f"case_{index}"),
                query=str(item["query"]),
                expected=expected,
                profile=dict(item.get("profile", {})),
                setup=dict(item.get("setup", {})),
                tags=list(item.get("tags", [])),
                reference_response=str(item.get("reference_response", "")),
                candidate_response=str(item.get("candidate_response", "")),
                retrieved_docs=list(item.get("retrieved_docs", [])),
            )
        )
    return cases
