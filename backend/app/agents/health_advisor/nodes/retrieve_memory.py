import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.health_advisor.state import HealthAdvisorState
from app.memory.long_term import long_term_memory

logger = logging.getLogger(__name__)

async def retrieve_memory(
    state: HealthAdvisorState,
    db: AsyncSession,
) -> HealthAdvisorState:
    """Load only the memory slices required by the memory routing policy."""
    context = dict(state.get("context") or {})
    policy = state.get("memory_policy") or {}
    user_id = state.get("user_id", "")
    session_id = state.get("session_id", "")
    user_message = state.get("user_message", "")

    short_history = context.get("short_term_history") or []
    selected_short = short_history[-8:] if policy.get("needs_short_term") else []
    selected_long = []

    if policy.get("needs_long_term"):
        try:
            selected_long = await long_term_memory.search_relevant_messages(
                db,
                user_id,
                user_message,
                days=180,
                candidate_limit=120,
                limit=8,
                exclude_session_id=session_id
            )
            logger.info("[retrieve_memory] loaded %d long-term memory messages", len(selected_long))
        except Exception:
            logger.exception("[retrieve_memory] failed to load-term memories")
            selected_long = []

    state["retrieved_short_term_memories"] = selected_short
    state["retrieved_long_term_memories"] = selected_long
    context["selected_short_term_history"] = selected_short
    context["long_term_memories"] = selected_long
    state["context"] = context
    state["next_node"] = "plan_tasks"
    return state
