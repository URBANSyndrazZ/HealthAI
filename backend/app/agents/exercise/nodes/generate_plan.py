"""Generate personalized workout plan through the exercise tool registry."""

import logging
from typing import Any

import app.tools.exercise  # noqa: F401 - registers exercise tools
from app.tools.executor import ToolExecutionContext, append_tool_trace, tool_executor

logger = logging.getLogger(__name__)


def generate_plan(state: dict[str, Any]) -> dict[str, Any]:
    """Generate a deterministic baseline workout plan through a registered tool."""
    logger.info("[generate_plan] Generating workout plan via tool")
    tool_result = tool_executor.execute_sync(
        "generate_exercise_plan",
        context=ToolExecutionContext(
            agent_name="exercise",
            trace_id=str(state.get("trace_id", "")),
            user_id=str(state.get("user_id", "")),
            session_id=str(state.get("session_id", "")),
            required=True,
        ),
        fitness_level=state.get("fitness_level", "beginner"),
        fitness_goals=state.get("fitness_goals", ["健康"]),
        health_conditions=state.get("health_conditions", []),
        time_available=state.get("time_available", 30),
    )
    append_tool_trace(state, tool_result)
    if tool_result.status != "success":
        state.setdefault("safety_notes", []).append(
            tool_result.error.get("message", "运动计划工具暂不可用") if tool_result.error else "运动计划工具暂不可用"
        )
        state["workout_plan"] = {}
        state["exercises"] = []
        return state

    result = tool_result.data or {}

    state["workout_plan"] = result.get("workout_plan", {})
    state["exercises"] = result.get("exercises", [])
    state["safety_notes"] = result.get("safety_notes", [])
    logger.info(
        "[generate_plan] Tool generated %s plan with %d exercises for %s",
        state["workout_plan"].get("plan_type", "unknown"),
        len(state["exercises"]),
        state.get("fitness_level", "beginner"),
    )
    return state
