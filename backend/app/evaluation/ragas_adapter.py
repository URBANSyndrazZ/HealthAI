"""Optional Ragas integration for RAG answer evaluation."""

from __future__ import annotations

from typing import Any


def build_ragas_records(case_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert internal evaluation results into a Ragas-friendly record shape."""
    records: list[dict[str, Any]] = []
    for result in case_results:
        answer = result.get("answer") or ""
        contexts = [
            str(doc.get("content") or "")
            for doc in result.get("retrieved_docs", [])
            if doc.get("content")
        ]
        if not answer or not contexts:
            continue
        records.append(
            {
                "user_input": result.get("query", ""),
                "response": answer,
                "retrieved_contexts": contexts,
                "reference": result.get("reference_response") or answer,
            }
        )
    return records


def run_ragas_evaluation(case_results: list[dict[str, Any]]) -> dict[str, Any]:
    """Run Ragas when optional dependencies are installed.

    Ragas is intentionally not a hard dependency of the backend runtime. This
    adapter returns a skipped report when the package is not available.
    """
    records = build_ragas_records(case_results)
    if not records:
        return {
            "skipped": True,
            "reason": "No cases contain both answer text and retrieved contexts.",
        }

    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.metrics import (
            answer_relevancy,
            context_precision,
            context_recall,
            faithfulness,
        )
    except ImportError as exc:
        return {
            "skipped": True,
            "reason": f"Ragas dependencies are not installed: {exc}",
            "required_packages": ["ragas", "datasets"],
        }

    try:
        dataset = Dataset.from_list(records)
        score = evaluate(
            dataset,
            metrics=[
                answer_relevancy,
                faithfulness,
                context_precision,
                context_recall,
            ],
        )
        return {
            "skipped": False,
            "case_count": len(records),
            "scores": dict(score),
        }
    except Exception as exc:
        return {
            "skipped": True,
            "reason": f"Ragas evaluation failed: {type(exc).__name__}: {exc}",
        }
