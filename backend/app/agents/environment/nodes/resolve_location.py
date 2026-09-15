import logging
from typing import Any

import app.tools.environment  # noqa: F401 - registers environment tools
from app.tools.executor import ToolExecutionContext, append_tool_trace, tool_executor

logger = logging.getLogger(__name__)


def resolve_location_from_text(query: str, state: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve a city from free text through the registered tool."""
    result = tool_executor.execute_sync(
        "resolve_location",
        context=ToolExecutionContext(
            agent_name="environment",
            trace_id=str((state or {}).get("trace_id", "")),
            user_id=str((state or {}).get("user_id", "")),
            session_id=str((state or {}).get("session_id", "")),
            required=True,
        ),
        query=query,
    )
    if state is not None:
        append_tool_trace(state, result)
    if result.status != "success":
        raise RuntimeError(result.error.get("message", "resolve_location failed") if result.error else "resolve_location failed")
    return result.data

def resolve_location(state: dict[str, Any]) -> dict[str, Any]:
    """Resolve location from user query and update EnvironmentAgent state."""
    logger.info("[resolve_location] Resolving user location via tool")
    query = state.get("location_query") or state.get("user_message", "")
    location = resolve_location_from_text(query, state)
    state["location"] = location
    logger.info(
        "[resolve_location] Location resolved by tool: %s (%s, %s)",
        location.get("city"),
        location.get("lat"),
        location.get("lon"),
    )
    return state
