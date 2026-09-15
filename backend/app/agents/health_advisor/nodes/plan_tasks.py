import logging
import re

from app.agents.health_advisor.state import HealthAdvisorState
from app.agents.protocol import AgentTask

logger = logging.getLogger(__name__)

NUTRITION_KEYWORDS = {
    "吃",
    "饮食",
    "营养",
    "热量",
    "卡路里",
    "蛋白质",
    "脂肪",
    "碳水",
    "减脂餐",
    "早餐",
    "午餐",
    "晚餐",
}

ENVIRONMENT_KEYWORDS = {
    "天气",
    "空气",
    "雾霾",
    "pm2.5",
    "pm25",
    "aqi",
    "紫外线",
    "温度",
    "湿度",
    "过敏原",
    "户外",
}

EXERCISE_KEYWORDS = {
    "运动",
    "锻炼",
    "训练",
    "健身",
    "跑步",
    "慢跑",
    "力量",
    "有氧",
    "瑜伽",
    "拉伸",
    "减脂",
    "增肌",
}

LOCATION_PATTERN = re.compile(r"(北京|上海|广州|深圳|杭州|成都|南京|武汉|西安|重庆|天津|苏州|[一-龥]{2,6}(?:市|区|县))")
TIME_PATTERN = re.compile(r"(\d{1,3})\s*(?:分钟|min)")

def _contains_any(text: str, keywords: set[str]) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in keywords)

def _extract_location(message: str, profile: dict) -> str:
    match = LOCATION_PATTERN.search(message)
    if match:
        return match.group(1)

    basic_info = profile.get("basic_info", {}) if isinstance(profile, dict) else {}
    for key in ("city", "location", "address"):
        if basic_info.get(key):
            return str(basic_info[key])
        if isinstance(profile, dict) and profile.get(key):
            return str(profile[key])

    return ""

def _infer_fitness_goal(message: str) -> str:
    if "增肌" in message or "力量" in message:
        return "增肌"
    if "减脂" in message or "减肥" in message or "瘦" in message:
        return "减脂"
    if "跑步" in message or "有氧" in message:
        return "提升心肺"
    return "健康改善"

def _infer_fitness_level(message: str, profile: dict) -> str:
    lowered = message.lower()
    if "advanced" in lowered or "高阶" in message or "进阶" in message:
        return "advanced"
    if "intermediate" in lowered or "中级" in message or "有基础" in message:
        return "intermediate"
    exercise_profile = profile.get("exercise", {}) if isinstance(profile, dict) else {}
    return exercise_profile.get("fitness_level", "beginner")

def _infer_time_minutes(message: str) -> int:
    match = TIME_PATTERN.search(message)
    if not match:
        return 30
    minutes = int(match.group(1))
    return max(5, min(minutes, 180))

async def plan_tasks(state: HealthAdvisorState) -> HealthAdvisorState:
    """Plan specialist-agent tasks from the classification intent and message."""
    user_message = state.get("user_message", "")
    intent = state.get("intent", "")
    profile = state.get("context", {}).get("profile", {})

    has_nutrition = _contains_any(user_message, NUTRITION_KEYWORDS) or intent in {"nutrition", "diet", "meal_analysis"}
    has_environment = _contains_any(user_message, ENVIRONMENT_KEYWORDS) or intent in {"environment", "weather", "air_quality"}
    has_exercise = _contains_any(user_message, EXERCISE_KEYWORDS) or intent in {"exercise", "fitness", "workout"}

    tasks: list[AgentTask] = []
    location = _extract_location(user_message, profile)

    if has_nutrition:
        tasks.append(
            AgentTask(
                task_id="nutrition_analysis",
                agent_name="nutrition",
                task_type="meal_analysis",
                payload={"description": user_message},
                timeout_seconds=20,
                retry=1
            )
        )

    if has_environment:
        tasks.append(
            AgentTask(
                task_id="environment_analysis",
                agent_name="environment",
                task_type="environment_query",
                payload={
                    "location": location or user_message,
                    "query_type": "all",
                },
                timeout_seconds=20,
                retry=1,
            )
        )

    if has_exercise:
        depends_on = ["environment_analysis"] if has_environment else []
        tasks.append(
            AgentTask(
                task_id="exercise_plan",
                agent_name="exercise",
                task_type="workout_plan",
                payload={
                    "goal": _infer_fitness_goal(user_message),
                    "fitness_level": _infer_fitness_level(user_message, profile),
                    "time_minutes": _infer_time_minutes(user_message),
                    "location": "outdoor" if has_environment or "户外" in user_message else "home",
                },
                depends_on=depends_on,
                timeout_seconds=25,
                retry=1,
            )
        )

    state["sub_tasks"] = [task.model_dump() for task in tasks]
    state["orchestration_status"] = "planned" if tasks else "not_required"
    state["next_node"] = "dispatch_agents" if tasks else "rag_retrieve"

    logger.info("Planned %d sub-agent tasks for intent=%s", len(tasks), intent)
    return state