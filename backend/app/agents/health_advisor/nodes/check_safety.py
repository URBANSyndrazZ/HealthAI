import logging

from app.agents.health_advisor.prompts import SAFETY_CHECK_PROMPT
from app.agents.health_advisor.state import HealthAdvisorState
from app.core.prompt_security import assess_prompt_injection
# from app.core.prompt_security import assess_prompt_injection
from app.llm.deepseek import deepseek_client

logger = logging.getLogger(__name__)

# Urgent keywords that trigger immediate escalation
URGENT_KEYWORDS = [
    "胸痛", "胸口痛", "心脏痛",
    "呼吸困难", "呼吸急促", "喘不过气",
    "昏迷", "晕倒", "意识丧失",
    "大出血", "流血不止",
    "严重过敏", "呼吸困难",
    "中风", "面瘫", "肢体无力",
    "自杀", "想死", "不想活",
    "120", "急救", "急诊",
]

def _check_urgent_keywords(message: str) -> tuple[bool, str]:
    """Check if message contains urgent keywords.

    Returns:
        (is_urgent, reason)
    """
    message_lower = message.lower()
    for keyword in URGENT_KEYWORDS:
        if keyword in message_lower:
            return True, f"检测到紧急关键词: {keyword}"
    return False, ""

async def check_safety(state: HealthAdvisorState) -> HealthAdvisorState:
    """Check user message for safety concerns.

    Performs two-level safety check:
    1. Keyword-based detection for urgent symptoms
    2. LLM-based analysis for nuanced safety concerns

    Args:
        state: Current state with user message

    Returns:
        Updated state with safety assessment
    """
    user_message = state.get("user_message", "")

    logger.info(f"Checking safety for message: {user_message[:100]}...")

    prompt_security = assess_prompt_injection(user_message)
    state["prompt_security"] = prompt_security.model_dump()
    if prompt_security.is_suspicious:
        logger.warning(
            "Prompt injection suspected categories=%s risk=%s",
            prompt_security.categories,
            prompt_security.risk_level,
        )
        state.setdefault("agent_warnings", []).append(prompt_security.warning)

    # Level1: Keyword check
    is_urgent_keyword, keyword_reason = _check_urgent_keywords(user_message)

    if is_urgent_keyword:
        logger.warning(f"Urgent keywords detected: {keyword_reason}")
        state["safety_flag"] = {
            "is_urgent": True,
            "risk_level": "high",
            "warning_message": "您的描述可能涉及紧急医疗情况，请立即拨打120或前往最近的医院急诊室。不要等待在线回复。",
            "recommendations": ["立即拨打120", "前往最近的医院急诊室", "不要延误"],
            "reason": keyword_reason,
        }
        state["next_node"] = "urgent_reply"
        return state

    # Level 2: LLM-based safety check (for non-obvious cases)
    try:
        result = await deepseek_client.json_chat(
            system_prompt= f"你是一个专门分析健康咨询安全性的AI助手\n {SAFETY_CHECK_PROMPT}",
            user_message=user_message,
        )

        is_urgent = result.get("is_urgent", False)
        risk_level = result.get("risk_level", "low")

        if is_urgent and risk_level in ["medium", "high"]:
            logger.warning(f"LLM detected urgent safety concern: {result}")
            state["safety_flag"] = {
                "is_urgent": True,
                "risk_level": "high",
                "warning_message": result.get("warning_message", "您的描述可能涉及紧急医疗情况，请立即拨打120或前往最近的医院急诊室。不要等待在线回复。"),
                "recommendations": result.get("recommendations", ["立即拨打120", "前往医院急诊"]),
                "reason": "LLM safety check detected urgent concern"
            }
            state["next_node"] = "urgent_reply"
        else:
            state["safety_flag"] = {
                "is_urgent": False,
                "risk_level": "low",
                "warning_message": None,
                "recommendations": []
            }
            state["next_node"] = "classify_intent"
    except Exception as e:
        logger.error(f"Safety check failed: {e}")
        # Fail safe - assume not urgent
        state["safety_flag"] = {
            "is_urgent": False,
            "risk_level": "low",
            "warning_message": None,
            "recommendations": []
        }
        state["next_node"] = "classify_intent"

    return state