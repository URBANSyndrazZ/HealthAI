"""Optional live RAG retrieval for evaluation suites."""

from __future__ import annotations

import time
from typing import Any

from app.rag.retriever import rag_retriever


def normalize_retrieved_doc(doc: dict[str, Any]) -> dict[str, Any]:
    """Keep only evaluation-safe fields from a retrieved document."""
    metadata = doc.get("metadata") or {}
    return {
        "id": doc.get("id"),
        "title": doc.get("title", ""),
        "content": doc.get("content", ""),
        "source": doc.get("source", ""),
        "metadata": metadata,
        "score": doc.get("score"),
        "retrieval": doc.get("retrieval", {}),
    }


async def retrieve_live_rag(query: str) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """Retrieve documents from the configured Elasticsearch RAG index.

    The caller receives an error object instead of an exception so that a JSON
    evaluation report can still explain which external dependency failed.
    """
    started_at = time.perf_counter()
    try:
        docs = await rag_retriever.retrieve(query)
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        return [normalize_retrieved_doc(doc) for doc in docs], {"elapsed_ms": elapsed_ms}
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        return [], {
            "elapsed_ms": elapsed_ms,
            "error": type(exc).__name__,
            "message": str(exc),
        }
