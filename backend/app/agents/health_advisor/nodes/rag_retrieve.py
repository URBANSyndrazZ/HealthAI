import logging
import time

from app.agents.health_advisor.state import HealthAdvisorState
from app.rag.retriever import rag_retriever

logger = logging.getLogger(__name__)


async def rag_retrieve(state: HealthAdvisorState) -> HealthAdvisorState:
    """Retrieve relevant knowledge for the user query.

    Uses the RAG retriever to find relevant health knowledge
    based on the user's question.

    Args:
        state: Current state with user message

    Returns:
        Updated state with retrieved documents
    """
    user_message = state.get("user_message", "")

    logger.info(f"Retrieving knowledge for: {user_message[:100]}...")

    try:
        started_at = time.perf_counter()
        # Initialize retriever if needed
        await rag_retriever.initialize()

        # Retrieve relevant documents
        docs = await rag_retriever.retrieve(user_message)

        logger.info(
            "Retrieved %d documents in %.2fs",
            len(docs),
            time.perf_counter() - started_at,
        )

        # Update state
        state["retrieved_docs"] = docs
        state["next_node"] = "generate_response"

    except Exception:
        logger.exception("RAG retrieval failed")
        # Continue without retrieved docs
        state["retrieved_docs"] = []
        state["next_node"] = "generate_response"

    return state