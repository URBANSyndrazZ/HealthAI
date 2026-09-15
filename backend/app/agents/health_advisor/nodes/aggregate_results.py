import logging
from typing import Any

from app.agents.health_advisor.state import HealthAdvisorState

logger = logging.getLogger(__name__)


def _compact_result(agent_name: str, result: dict[str, Any]) -> dict[str, Any]:
    """Keep the fields that are most useful for final answer generation."""
    if agent_name == "nutrition":
        return {
            "foods": result.get("extracted_foods", []),
            "total_nutrition": result.get("total_nutrition", {}),
            "health_score": result.get("health_score"),
            "recommendations": result.get("recommendations", []),
            "response": result.get("response", ""),
        }
    if agent_name == "environment":
        return {
            "location": result.get("location"),
            "air_quality": result.get("air_quality"),
            "weather": result.get("weather"),
            "health_risk": result.get("health_risk"),
            "recommendations": result.get("recommendations", []),
            "response": result.get("response", ""),
        }
    if agent_name == "exercise":
        return {
            "workout_plan": result.get("workout_plan", {}),
            "exercises": result.get("exercises", []),
            "safety_notes": result.get("safety_notes", []),
            "response": result.get("response", ""),
        }
    return result


async def aggregate_results(state: HealthAdvisorState) -> HealthAdvisorState:
    """Normalize specialist-agent outputs for the final response nodes."""
    responses = state.get("sub_agent_results", {})
    aggregated: dict[str, Any] = {}
    warnings: list[str] = []
    tool_trace: list[dict[str, Any]] = list(state.get("tool_trace") or [])

    for task_id, response in responses.items():
        agent_name = response.get("agent_name", task_id)
        status = response.get("status", "failed")
        metadata = response.get("metadata") or {}
        response_tool_trace = metadata.get("tool_trace") or []
        if status not in {"success", "partial"}:
            tool_trace.extend(response_tool_trace)
            error = response.get("error") or {}
            warnings.append(f"{agent_name} 子任务未完成：{error.get('message', status)}")
            continue

        result = response.get("result") or {}
        tool_trace.extend(response_tool_trace or result.get("tool_trace") or [])
        aggregated[agent_name] = {
            "task_id": task_id,
            "summary": response.get("summary", ""),
            "confidence": response.get("confidence"),
            "warnings": response.get("warnings", []),
            "data": _compact_result(agent_name, result),
        }
        warnings.extend(response.get("warnings", []))

    state["aggregated_agent_context"] = aggregated
    state["agent_warnings"] = warnings
    state["tool_trace"] = tool_trace
    if aggregated:
        state["orchestration_status"] = (
            "success" if state.get("orchestration_status") == "success" else "partial"
        )

    logger.info("Aggregated %d specialist agent results", len(aggregated))
    state["next_node"] = "rag_retrieve"
    return state