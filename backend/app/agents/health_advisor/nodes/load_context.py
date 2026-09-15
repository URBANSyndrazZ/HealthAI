import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.health_advisor.state import HealthAdvisorState
from app.memory.profile import profile_manager
from app.memory.medium_term import medium_term_memory
from app.memory.short_term import short_term_memory
from app.services.health_service import HealthService
from app.models import ChatMessage

logger = logging.getLogger(__name__)

async def load_context(
    state: HealthAdvisorState,
    db: AsyncSession,
) -> HealthAdvisorState:
    """Load context for the current conversation.

    Loads:
    - User profile from database
    - Recent conversation history (short-term memory)
    - Health data context

    Note:
    - Long-term memory retrieval is handled later by the memory routing stage.

    Args:
        state: Current state
        db: Database session

    Returns:
        Updated state with loaded context
    """
    user_id = state["user_id"]
    session_id = state["session_id"]

    logging.info(f"Loading context for user {user_id}, session {session_id}")

    existing_context = state.get("context", {}) or {}

    # Initialize context
    context = {
        "profile": existing_context.get("profile", {}),
        "medium_term_summary": existing_context.get("medium_term_summary", ""),
        "short_term_history": existing_context.get("short_term_history", []),
        "long_term_memories": existing_context.get("long_term_memories", []),
        "health_data": existing_context.get("health_data", {}),
    }

    try:
        # Load user profile
        profile = await profile_manager.load_profile(db, user_id)
        if profile:
            context["profile"] = profile
        logger.debug(f"Loaded profile for user {user_id}")
    except Exception as e:
        logger.warning(f"Failed to load profile for user {user_id}: {e}")

    short_history = []
    try:
        short_history = await short_term_memory.get_history(user_id, session_id)
    except Exception:
        logger.exception("Failed to load short-term memory from backend")

    if not short_history:
        try:
            result = await db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
                .limit(50)
            )
            db_messages = list(reversed(result.scalars().all()))
            short_history = [
                {
                    "id": message.id,
                    "role": message.role,
                    "message": message.content,
                    "created_at": message.created_at.isoformat() if message.created_at else "",
                }
                for message in db_messages
            ]
            if short_history:
                await short_term_memory.hydrate_from_db(user_id, session_id, short_history)
        except Exception:
            logger.exception("Failed to rebuild short-term memory from database")

    context["short_term_history"] = short_history
    logger.debug("Loaded %d short-term memory messages", len(short_history))

    try:
        medium_term_summary = await medium_term_memory.get_summary(db, session_id)
        context["medium_term_summary"] = medium_term_summary
        if medium_term_summary:
            logger.debug("Loaded medium-term summary for session %s", session_id)
    except Exception:
        logger.exception("Failed to load medium-term memory for session %s", session_id)

    try:
        health_data = await HealthService(db).get_agent_context(user_id, days=30)
        context["health_data"] = health_data
        logger.debug(
            "Loaded health context for user %s with %d latest record groups",
            user_id, len(health_data.get("latest_records", {}))
        )
    except Exception as e:
        logger.warning(f"Failed to laod health data context: {e}")

    # Update state with loaded context (兼容非图模式的调用链设计)
    state["context"] = context
    state["next_node"] = "classify_intent"

    return state
