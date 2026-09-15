import asyncio
import logging
import re

from app.agents.health_advisor.prompts import FOLLOWUP_QUESTIONS_PROMPT
from app.agents.health_advisor.state import HealthAdvisorState
from app.llm.deepseek import deepseek_client
from app.memory.long_term import long_term_memory
from app.memory.profile import profile_manager
from app.models.database import async_session
from app.services.suggested_questions import filter_suggested_questions

logger = logging.getLogger(__name__)

CONDITION_WORDS = ("高血压", "糖尿病", "高血脂", "脂肪肝", "痛风", "哮喘", "冠心病", "胃病")
GOAL_WORDS = ("减脂", "减肥", "增肌", "控糖", "降压", "改善睡眠", "提高体能", "增强体质")

def _extract_profile_from_response(response: str, user_message: str) -> dict:
    """Extract structured profile updates from conversation.

    Structured fields are persisted to PostgreSQL user_profiles. Free-form
    habits and preferences are handled separately by the ES long-term memory.
    """
    extracted = {}
    message = re.sub(r"\s+", " ", str(user_message or "")).strip()
    if not message:
        return extracted

    age_match = re.search(r"(\d{1,3})[\s]*岁", message)
    if age_match:
        extracted.setdefault("basic_info", {})
        extracted["basic_info"]["age"] = int(age_match.group(1))

    if any(keyword in message for keyword in ("我是男", "男性", "男生")):
        extracted.setdefault("basic_info", {})
        extracted["basic_info"]["gender"] = "male"
    elif any(keyword in message for keyword in ("我是女", "女性", "女生")):
        extracted.setdefault("basic_info", {})
        extracted["basic_info"]["gender"] = "female"

    if "过敏" in message:
        allergy_pattern = r"(?:对|吃)?([\u4e00-\u9fa5A-Za-z0-9]{1,12})过敏"
        matches = [
            match
            for match in re.findall(allergy_pattern, message)
            if match not in {"我", "自己", "有点", "严重"}
        ]
        if matches:
            extracted.setdefault("health_status", {})
            extracted["health_status"].setdefault("allergies", [])
            for match in matches:
                if match not in extracted["health_status"]["allergies"]:
                    extracted["health_status"]["allergies"].append(match)

    conditions = [
        condition
        for condition in CONDITION_WORDS
        if any(pattern in message for pattern in (f"我有{condition}", f"我得了{condition}", f"患有{condition}"))
    ]
    if conditions:
        extracted.setdefault("health_status", {})
        extracted["health_status"].setdefault("conditions", [])
        for condition in conditions:
            if condition not in extracted["health_status"]["conditions"]:
                extracted["health_status"]["conditions"].append(condition)

    goals = [goal for goal in GOAL_WORDS if goal in message and "我" in message]
    if goals:
        extracted["health_goals"] = goals

    diet_avoidances = re.findall(r"(?:不吃|忌口|避免吃)([\u4e00-\u9fa5A-Za-z0-9]{1,12})", message)
    diet_likes = re.findall(r"(?:喜欢吃|爱吃)([\u4e00-\u9fa5A-Za-z0-9]{1,12})", message)
    if diet_avoidances or diet_likes:
        extracted.setdefault("diet_preferences", {})
    if diet_avoidances:
        extracted["diet_preferences"]["avoid"] = list(dict.fromkeys(diet_avoidances))
    if diet_likes:
        extracted["diet_preferences"]["likes"] = list(dict.fromkeys(diet_likes))

    return extracted

async def _generate_followup_questions(user_message: str, response: str, profile: list[str]) -> list[str]:
    """Generate follow-up questions.

    Args:
        user_message: Original user message
        response: Generated response
        profile: User profile

    Returns:
        List of follow-up questions
    """
    try:
        prompt = FOLLOWUP_QUESTIONS_PROMPT.format(
            user_message=user_message,
            response=response,
            profile=str(profile)
        )

        result = await deepseek_client.json_chat(
            system_prompt="你是一个帮助生成健康咨询后续问题的AI助手。",
            user_message=prompt
        )

        # Handle different result formats
        questions = []
        if isinstance(result, dict):
            questions = result.get("questions", [])
        elif isinstance(result, list):
            questions = result

        filtered = filter_suggested_questions(
            questions if isinstance(questions, list) else [],
            current_question=user_message,
            fallback=_fallback_followup_questions(user_message, response)
        )
        if filtered:
            return filtered

        # Fallback questions
        return _fallback_followup_questions(user_message, response)

    except Exception as e:
        logger.error(f"Follow-up question generation failed: {e}")
        return _fallback_followup_questions(user_message, response)

def _fallback_followup_questions(user_message: str, response: str = "") -> list[str]:
    """Build topic-aware fallback follow-up questions."""
    text = f"{user_message} {response}"
    if any(keyword in text for keyword in ("运动", "跑步", "锻炼", "健身", "活动量")):
        return [
            "结合我的情况安排一周运动计划？",
            "怎么判断运动强度是否合适？",
            "运动后需要注意哪些恢复事项？",
        ]
    if any(keyword in text for keyword in ("饮食", "早餐", "晚餐", "营养", "蛋白", "减脂", "控糖")):
        return [
            "帮我制定一天的饮食搭配？",
            "哪些食物更适合我的目标？",
            "这类饮食有什么注意事项？",
        ]
    if any(keyword in text for keyword in ("睡眠", "作息", "熬夜", "失眠", "早醒")):
        return [
            "怎么制定可执行的作息计划？",
            "睡前有哪些习惯需要调整？",
            "如何判断睡眠是否改善？",
        ]
    if any(keyword in text for keyword in ("天气", "空气", "温度", "湿度", "户外")):
        return [
            "今天适合安排什么运动？",
            "户外运动需要注意什么？",
            "空气不好时如何替代训练？",
        ]
    return [
        "结合我的情况下一步怎么做？",
        "有哪些需要重点注意的风险？",
        "可以帮我制定一个执行计划吗？",
    ]

async def _persist_profile_update(user_id: str, extracted_profile: dict, db=None) -> bool:
    """Persist structured profile fields to PostgreSQL."""
    if not user_id or not extracted_profile:
        return False

    if db is not None:
        return await profile_manager.update_profile(db, user_id, extracted_profile)

    async with async_session() as session:
        return await profile_manager.update_profile(session, user_id, extracted_profile)

async def _profile_update_background_task(user_id: str, extracted_profile: dict):
    try:
        updated = await _persist_profile_update(user_id, extracted_profile)
        logger.info(
            "Structured profile background update %s for user %s",
            "finished" if updated else "skipped",
            user_id,
        )
    except Exception:
        logger.exception("Structured profile background update failed for user %s", user_id)

def _trigger_profile_update(user_id: str, extracted_profile: dict) -> bool:
    """Schedule structured profile persistence without blocking the response."""
    if not user_id or not extracted_profile:
        return False

    try:
        asyncio.create_task(_profile_update_background_task(user_id, extracted_profile))
        return True
    except RuntimeError:
        logger.exception("Failed to schedule structured profile update for user %s", user_id)
        return False

async def post_process(
    state: HealthAdvisorState,
    db=None,  # Optional db session for background tasks
) -> HealthAdvisorState:
    """Post-process the response.

    Performs:
    1. Generate follow-up questions
    2. Extract structured profile updates and trigger async persistence
    3. Extract and persist long-term semantic memories

    Args:
        state: Current state with generated response
        db: Optional database session for background tasks

    Returns:
        Updated state with post-processing results
    """
    user_message = state.get("user_message", "")
    response = state.get("response", "")
    profile = state.get("context", {}).get("profile", {})
    user_id = state.get("user_id", "")
    session_id = state.get("session_id", "")

    logger.info("Post-processing response")

    # 1. Generate follow-up questions
    try:
        suggested_questions = await _generate_followup_questions(
            user_message, response, profile
        )
        state["suggested_questions"] = suggested_questions
        logger.info(f"Generated {len(suggested_questions)} follow-up questions")
    except Exception as e:
        logger.error(f"Failed to generate follow-up questions: {e}")
        state["suggested_questions"] = [
            "您还有其他健康方面的问题吗？",
            "您想了解更多关于这方面的信息吗？",
        ]

    # 2. Extract profile updates (simple keyword-based extraction)
    try:
        extracted_profile = _extract_profile_from_response(response, user_message)
        if extracted_profile:
            logger.info(f"Extracted profile updates: {extracted_profile}")
            state["extracted_profile"] = extracted_profile
            state["profile_update_scheduled"] = _trigger_profile_update(user_id, extracted_profile)
            state["profile_updated"] = False
    except Exception as e:
        logger.error(f"Profile extraction failed: {e}")

    # 3. Extract and persist long-term semantic memories into Elasticsearch.
    try:
        stored_memory_ids = await long_term_memory.store_user_message_memories(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            extracted_profile=state.get("extracted_profile", {})
        )
        state["stored_memory_ids"] = stored_memory_ids
        if stored_memory_ids:
            logger.info("Stored %d long-term memory facts", len(stored_memory_ids))
    except Exception as e:
        logger.error(f"Failed to update long-term memory: {e}")

    # Mark as complete
    state["next_node"] = "end"

    return state
