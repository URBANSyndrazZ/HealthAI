"""Fetch weather data through the environment tool registry."""

import logging
from typing import Any

import app.tools.environment  # noqa: F401 - registers environment tools
from app.agents.environment.nodes.resolve_location import resolve_location_from_text
from app.tools.environment import get_weather_desc
from app.tools.executor import ToolExecutionContext, append_tool_trace, tool_executor

logger = logging.getLogger(__name__)


def fetch_weather(state: dict[str, Any]) -> dict[str, Any]:
    """Fetch weather data for the state location through a registered tool."""
    logger.info("[fetch_weather] Fetching weather data via tool")
    api_errors = state.setdefault("api_errors", [])

    location = state.get("location")
    if not location:
        location = resolve_location_from_text(state.get("location_query") or state.get("user_message", ""), state)
        state["location"] = location
        api_errors.append("Location was missing before weather query; resolved from message")
        logger.warning("[fetch_weather] Location missing, resolved fallback: %s", location.get("city"))

    result = tool_executor.execute_sync(
        "fetch_weather",
        context=ToolExecutionContext(
            agent_name="environment",
            trace_id=str(state.get("trace_id", "")),
            user_id=str(state.get("user_id", "")),
            session_id=str(state.get("session_id", "")),
            required=False,
        ),
        location=location,
        user_message=state.get("user_message", ""),
    )
    append_tool_trace(state, result)
    if result.status != "success":
        api_errors.append(result.error.get("message", "Weather tool failed") if result.error else "Weather tool failed")
        state["weather"] = {}
        return state

    payload = result.data or {}
    state["weather"] = payload.get("weather", {})
    api_errors.extend(payload.get("api_errors", []))
    weather = state["weather"]
    logger.info(
        "[fetch_weather] Tool result %s: %s°C/%s°C, %s source=%s",
        weather.get("target_date"),
        weather.get("temp_low"),
        weather.get("temp_high"),
        weather.get("weather_description"),
        weather.get("data_source"),
    )
    return state
