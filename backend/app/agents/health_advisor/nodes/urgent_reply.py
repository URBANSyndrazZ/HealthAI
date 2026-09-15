import logging

from app.agents.health_advisor.state import HealthAdvisorState

logger = logging.getLogger(__name__)

# Urgent reply template
URGENT_REPLY_TEMPLATE = """🚨 **紧急医疗警告** 🚨

{warning_message}

**请立即采取以下行动：**

{recommendations}

---

**请记住：**
- 在线健康咨询不能替代紧急医疗服务
- 在紧急情况下，每一分钟都很重要
- 当有疑问时，请优先选择就医

如果您的情况不是紧急情况，请重新描述您的症状，我们将为您提供帮助。
"""

async def urgent_reply(state: HealthAdvisorState) -> HealthAdvisorState:
    """Generate urgent reply for emergency situations.

    Args:
        state: Current state with safety flag

    Returns:
        Updated state with urgent reply
    """
    safety_flag = state.get("safety_flag", {})

    logger.warning("Generating urgent reply for safety concern")

    if not safety_flag or not safety_flag.get("is_urgent"):
        logger.error("urgent_reply called without urgent safety flag")
        state["response"] = "系统出错, 请稍后重试"
        state["next_node"] = "end"
        return state

    # Build recommendations list
    recommendations = safety_flag.get("recommendations", [])
    if recommendations:
        recommendations_text = "\n".join([f"{i+1}. {rec}" for i, rec in enumerate(recommendations)])
    else:
        recommendations_text = "1. 立即拨打120\n2. 前往最近的医院急诊室"

    # Build urgent reply
    warning_message = safety_flag.get(
        "warning_message",
        "您的描述可能涉及紧急医疗情况，请立即拨打120或前往最近的医院急诊室。"
    )

    response = URGENT_REPLY_TEMPLATE.format(
        warning_message=warning_message,
        recommendations=recommendations_text
    )

    logger.info("Urgent reply generated")

    # Update state
    state["response"] = response
    state["safety_flag"] = safety_flag # Ensure safety flag is preserved
    state["next_node"] = "post_process"

    return state