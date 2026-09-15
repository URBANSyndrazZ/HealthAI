"""End-to-end HealthAdvisorAgent replay for enterprise-grade evaluation."""

from __future__ import annotations

import logging
import json
import time
from typing import Any

from app.agents.health_advisor.agent import HealthAdvisorAgent
from app.agents.health_advisor.state import HealthAdvisorState
from app.evaluation.cases import EvaluationCase
from app.memory.long_term import long_term_memory
from app.models.database import init_db


logger = logging.getLogger(__name__)


def _summarize_doc(doc: dict[str, Any]) -> dict[str, Any]:
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


def _task_agents(sub_tasks: list[dict[str, Any]]) -> list[str]:
    return [
        str(task.get("agent_name") or task.get("agent") or "")
        for task in sub_tasks
        if task.get("agent_name") or task.get("agent")
    ]


def _completed_agents(agent_trace: dict[str, Any], sub_agent_results: dict[str, Any]) -> list[str]:
    completed: set[str] = set()
    for item in agent_trace.get("completed", []) or []:
        if isinstance(item, str) and not item.endswith("_analysis") and item != "exercise_plan":
            completed.add(item)
    for response in sub_agent_results.values():
        if isinstance(response, dict) and response.get("status") in {"success", "partial"}:
            if response.get("agent_name"):
                completed.add(str(response["agent_name"]))
    return sorted(completed)


def _tool_context_docs(aggregated_context: dict[str, Any]) -> list[dict[str, Any]]:
    docs: list[dict[str, Any]] = []
    for agent_name, payload in aggregated_context.items():
        docs.append(
            {
                "id": f"tool_context_{agent_name}",
                "title": f"{agent_name} 子 Agent 结果",
                "content": json.dumps(payload, ensure_ascii=False, default=str),
                "source": "sub_agent_tool_context",
                "metadata": {"topic": agent_name, "category": "tool_context"},
            }
        )
    return docs


async def run_health_advisor_replay(
    case: EvaluationCase,
    *,
    initialize_dependencies: bool = True,
) -> dict[str, Any]:
    """Run one case through the complete HealthAdvisorAgent graph."""
    user_id = str(case.setup.get("user_id") or "eval_user")
    session_id = str(case.setup.get("session_id") or f"eval_{case.id}")

    if initialize_dependencies:
        await init_db()
        try:
            await long_term_memory.initialize()
        except Exception:
            logger.exception("[e2e_evaluation] long-term memory initialization failed")

    state = HealthAdvisorState(
        user_id=user_id,
        session_id=session_id,
        user_message=case.query,
        context={
            "profile": case.profile,
            "short_term_history": list(case.setup.get("short_term_history", [])),
        },
    )
    agent = HealthAdvisorAgent()
    started_at = time.perf_counter()
    logger.info("[e2e_evaluation] replay start case=%s session=%s", case.id, session_id)
    final_state = await agent.process(state)
    elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "[e2e_evaluation] replay finished case=%s elapsed_ms=%s status=%s",
        case.id,
        elapsed_ms,
        final_state.get("status", "ok"),
    )

    retrieved_docs = [_summarize_doc(doc) for doc in final_state.get("retrieved_docs", [])]
    sub_tasks = list(final_state.get("sub_tasks", []))
    sub_agent_results = dict(final_state.get("sub_agent_results", {}))
    agent_trace = dict(final_state.get("agent_trace", {}))
    aggregated_context = dict(final_state.get("aggregated_agent_context", {}))
    safety_flag = final_state.get("safety_flag") or {}
    prompt_security = final_state.get("prompt_security") or {}

    return {
        "elapsed_ms": elapsed_ms,
        "status": final_state.get("status", "ok"),
        "response": final_state.get("response", ""),
        "intent": final_state.get("intent", ""),
        "safety_flag": safety_flag,
        "prompt_security": prompt_security,
        "memory_policy": final_state.get("memory_policy") or {},
        "retrieved_docs": retrieved_docs,
        "task_agents": _task_agents(sub_tasks),
        "sub_tasks": sub_tasks,
        "orchestration_status": final_state.get("orchestration_status"),
        "completed_agents": _completed_agents(agent_trace, sub_agent_results),
        "agent_trace": agent_trace,
        "tool_context_docs": _tool_context_docs(aggregated_context),
        "citations": final_state.get("citations", []),
        "suggested_questions": final_state.get("suggested_questions", []),
        "stored_memory_ids": final_state.get("stored_memory_ids", []),
        "retrieved_short_term_count": len(final_state.get("retrieved_short_term_memories", [])),
        "retrieved_long_term_count": len(final_state.get("retrieved_long_term_memories", [])),
    }
