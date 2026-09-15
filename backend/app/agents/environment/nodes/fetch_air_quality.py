"""Fetch air quality data through the environment tool registry."""

import logging
from typing import Any

import app.tools.environment  # noqa: F401 - registers environment tools
from app.agents.environment.nodes.resolve_location import resolve_location_from_text
from app.tools.executor import ToolExecutionContext, append_tool_trace, tool_executor

logger = logging.getLogger(__name__)


def fetch_air_quality(state: dict[str, Any]) -> dict[str, Any]:
    """Fetch air quality data for the state location through a registered tool."""
    logger.info("[fetch_air_quality] Fetching air quality data via tool")
    api_errors = state.setdefault("api_errors", [])

    location = state.get("location")
    if not location:
        location = resolve_location_from_text(state.get("location_query") or state.get("user_message", ""), state)
        state["location"] = location
        api_errors.append("Location was missing before air quality query; resolved from message")
        logger.warning("[fetch_air_quality] Location missing, resolved fallback: %s", location.get("city"))

    result = tool_executor.execute_sync(
        "fetch_air_quality",
        context=ToolExecutionContext(
            agent_name="environment",
            trace_id=str(state.get("trace_id", "")),
            user_id=str(state.get("user_id", "")),
            session_id=str(state.get("session_id", "")),
            required=False,
        ),
        location=location,
    )
    append_tool_trace(state, result)
    if result.status != "success":
        api_errors.append(result.error.get("message", "Air quality tool failed") if result.error else "Air quality tool failed")
        state["air_quality"] = {}
        return state

    air_quality = result.data
    state["air_quality"] = air_quality
    logger.info(
        "[fetch_air_quality] Tool result AQI: %s (%s), PM2.5: %s",
        air_quality.get("aqi"),
        air_quality.get("level"),
        air_quality.get("pm25"),
    )
    return state
