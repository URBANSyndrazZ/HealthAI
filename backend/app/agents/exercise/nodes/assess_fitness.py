"""Assess user fitness level."""

import logging
import re
from typing import Dict, Any

logger = logging.getLogger(__name__)


def assess_fitness(state: Dict[str, Any]) -> Dict[str, Any]:
    """Assess user's fitness level based on profile and message."""
    logger.info("[assess_fitness] Assessing fitness level")

    user_message = state.get("user_message", "")
    user_profile = state.get("user_profile", {})

    # Default to beginner
    fitness_level = "beginner"
    fitness_goals = []
    health_conditions = []

    # Extract from user message
    msg_lower = user_message.lower()

    # Fitness level keywords
    if any(kw in msg_lower for kw in ["新手", "刚开始", "没有运动", "零基础", "beginner"]):
        fitness_level = "beginner"
    elif any(kw in msg_lower for kw in ["有一定基础", "中级", "偶尔运动", "intermediate"]):
        fitness_level = "intermediate"
    elif any(kw in msg_lower for kw in ["高级", "经常运动", "专业", "advanced", "expert"]):
        fitness_level = "advanced"

    # Fitness goals
    goal_keywords = {
        "减脂": ["减脂", "减肥", "瘦身", "减重", "fat loss", "weight loss"],
        "增肌": ["增肌", "增重", "塑形", "肌肉", "muscle", "strength"],
        "耐力": ["耐力", "心肺", "有氧", "endurance", "cardio"],
        "柔韧": ["柔韧", "拉伸", "瑜伽", "flexibility", "yoga"],
        "健康": ["健康", "保健", "养生", "health", "wellness"],
    }

    for goal, keywords in goal_keywords.items():
        if any(kw in msg_lower for kw in keywords):
            fitness_goals.append(goal)

    if not fitness_goals:
        fitness_goals.append("健康")  # Default goal

    # Health conditions
    health_keywords = ["心脏病", "高血压", "糖尿病", "哮喘", "关节炎", "腰间盘突出", "膝盖", "关节"]
    for keyword in health_keywords:
        if keyword in user_message:
            health_conditions.append(keyword)

    # Update state
    state["fitness_level"] = fitness_level
    state["fitness_goals"] = fitness_goals
    state["health_conditions"] = health_conditions

    # Create assessment summary
    state["assessment"] = {
        "fitness_level": fitness_level,
        "fitness_goals": fitness_goals,
        "health_conditions": health_conditions,
        "exercise_frequency": "unknown",
        "available_equipment": [],
    }

    logger.info(f"[assess_fitness] Fitness level: {fitness_level}, Goals: {fitness_goals}")

    return state
