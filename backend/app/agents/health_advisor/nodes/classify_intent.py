import inspect
import json
import logging

from app.agents.health_advisor.prompts import INTENT_CLASSIFICATION_PROMPT
from app.agents.health_advisor.state import HealthAdvisorState
from app.llm.deepseek import deepseek_client

logger = logging.getLogger(__name__)

async def classify_intent(state: HealthAdvisorState) -> HealthAdvisorState:
    """Classify user intent and detect urgency.

    Analyzes the user message to determine:
    - Intent category (general_health, symptom_check, urgent_concern, etc.)
    - Urgency level (low, medium, high)
    - Whether medical attention is required

    Args:
        state: Current state with user message

    Returns:
        Updated state with intent classification
    """
    user_message = state.get("user_message", "")

    logger.info(f"Classifying intent for message: {user_message[:100]} ...")

    try:
        # Call LLM for intent classification
        result = await deepseek_client.json_chat(
            system_prompt=f"你是一个专门分析健康咨询意图的AI助手。\n{INTENT_CLASSIFICATION_PROMPT}",
            user_message=user_message
        )

        # Parse result
        intent = result.get("intent", "general_health")
        confidence = result.get("confidence", 0.5)
        urgency = result.get("urgency", "low")
        requires_medical = result.get("requires_medical", False)

        logger.info(f"Intent classified: {intent}, urgency: {urgency}, confidence: {confidence}")

        # Update state
        state["intent"] = intent
        state["intent_confidence"] = confidence
        state["urgency"] = urgency
        state["requires_medical"] = requires_medical

        # Determine next nodes based on urgency and intent
        if urgency == "high":
            state["next_node"] = "urgency_reply"
        else:
            state["next_node"] = "rag_retrieve"

    except Exception as e:
        logger.error(f"Intent classification failed: {e}")
        # Fallback to general health
        state["intent"] = "general_health"
        state["intent_confidence"] = 0.0
        state["urgency"] = "low"
        state["requires_medical"] = False
        state["next_node"] = "rag_retrieve"

    return state