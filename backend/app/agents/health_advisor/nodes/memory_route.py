import logging

from app.agents.health_advisor.state import HealthAdvisorState

logger = logging.getLogger(__name__)

SHORT_REFERENCE_MARKERS = (
    "刚才",
    "刚刚",
    "上一条",
    "上一个问题",
    "前面说",
    "前面提到",
    "刚提到",
    "刚说过",
    "之前说过",
)

LONG_REFERENCE_MARKERS = (
    "平时",
    "一直",
    "长期",
    "一贯",
    "通常",
    "以前",
    "过去",
    "历史",
)

KNOWLEDGE_MARKERS = (
    "建议",
    "推荐",
    "标准",
    "指南",
    "正常范围",
    "多少",
    "多大",
    "多久",
    "什么量",
    "身体活动量",
    "血压",
    "血糖",
    "BMI",
)

PERSONALIZATION_MARKERS = (
    "结合我",
    "根据我",
    "适合我",
    "我应该",
    "帮我安排",
    "给我计划",
    "怎么调整",
)

MEMORY_FACT_MARKERS = (
    "我一般",
    "我习惯",
    "我平时",
    "我通常",
    "我一直",
    "我以前",
)

def _build_policy(
    *,
    scope: str,
    needs_short_term: bool,
    needs_long_term: bool,
    needs_rag: bool,
    reason: str,
) -> dict:
    return {
        "scope": scope,
        "needs_short_term": needs_short_term,
        "needs_long_term": needs_long_term,
        "needs_rag": needs_rag,
        "reason": reason,
    }

async def memory_route(state: HealthAdvisorState) -> HealthAdvisorState:
    """Decide whether the current query needs short-term memory, long-term memory, or RAG."""
    message = str(state.get("user_message", "") or "")
    normalized = message.replace(" ", "")
    context = state.get("context", {})
    short_history = context.get("short_term_history") or []

    has_short_history = bool(short_history)
    mentions_recent_context = any(marker in normalized for marker in SHORT_REFERENCE_MARKERS)
    mentions_long_history = any(marker in normalized for marker in LONG_REFERENCE_MARKERS)
    asks_general_knowledge = any(marker in normalized for marker in KNOWLEDGE_MARKERS)
    asks_personalized_advice = any(marker in normalized for marker in PERSONALIZATION_MARKERS)
    asks_user_fact = any(marker in normalized for marker in MEMORY_FACT_MARKERS)
    mentions_self = any(token in normalized for token in ("我", "我的", "自己"))

    if mentions_recent_context and has_short_history:
        if asks_general_knowledge or asks_personalized_advice:
            policy = _build_policy(
                scope="short_and_rag",
                needs_short_term=True,
                needs_long_term=False,
                needs_rag=True,
                reason="用户在追问当前会话内容，并希望结合通用健康知识给出建议。",
            )
        else:
            policy = _build_policy(
                scope="short_only",
                needs_short_term=True,
                needs_long_term=False,
                needs_rag=False,
                reason="用户明确引用刚才/上一轮内容，优先只读取当前会话短期记忆。",
            )
    elif asks_general_knowledge and not mentions_self:
        policy = _build_policy(
            scope="rag_only",
            needs_short_term=False,
            needs_long_term=False,
            needs_rag=True,
            reason="问题主要在询问通用健康知识或标准，不依赖个人历史记忆。",
        )
    elif asks_personalized_advice and mentions_recent_context and has_short_history:
        policy = _build_policy(
            scope="short_and_rag",
            needs_short_term=True,
            needs_long_term=False,
            needs_rag=True,
            reason="问题需要结合当前会话上下文和外部知识进行个性化建议。",
        )
    elif asks_personalized_advice and (mentions_long_history or asks_user_fact or mentions_self):
        policy = _build_policy(
            scope="long_and_rag",
            needs_short_term=False,
            needs_long_term=True,
            needs_rag=True,
            reason="问题涉及用户长期习惯/偏好，且需要外部知识支撑建议。",
        )
    elif asks_user_fact:
        if has_short_history:
            policy = _build_policy(
                scope="short_only",
                needs_short_term=True,
                needs_long_term=False,
                needs_rag=False,
                reason="问题是在回忆本次会话里刚提到的个人事实，先只读短期记忆。",
            )
        else:
            policy = _build_policy(
                scope="long_only",
                needs_short_term=False,
                needs_long_term=True,
                needs_rag=False,
                reason="问题是在回忆用户长期事实/习惯，优先检索跨会话长期记忆。",
            )
    elif mentions_long_history:
        policy = _build_policy(
            scope="long_only",
            needs_short_term=False,
            needs_long_term=True,
            needs_rag=False,
            reason="用户显式提到长期/历史习惯，优先检索长期记忆。",
        )
    else:
        policy = _build_policy(
            scope="short_and_rag" if has_short_history else "rag_only",
            needs_short_term=has_short_history,
            needs_long_term=False,
            needs_rag=True,
            reason="默认策略：保留必要的近期上下文，并结合RAG知识回答。",
        )

    state["memory_policy"] = policy
    state["memory_policy_reason"] = policy["reason"]
    state["next_node"] = "retrieve_memory"
    logging.info(
        "[memory_route] scope=%s short=%s long=%s rag=%s reason=%s",
        policy["scope"],
        policy["needs_short_term"],
        policy["needs_long_term"],
        policy["needs_rag"],
        policy["reason"]
    )
    return state
