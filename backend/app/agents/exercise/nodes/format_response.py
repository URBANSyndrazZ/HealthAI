"""Format the final response for the Exercise Agent."""

import logging
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


def format_response(state: Dict[str, Any]) -> Dict[str, Any]:
    """Format the final response for the user."""
    logger.info("[format_response] Formatting final response")

    fitness_level = state.get("fitness_level", "beginner")
    fitness_goals = state.get("fitness_goals", [])
    workout_plan = state.get("workout_plan", {})
    exercises = state.get("exercises", [])
    safety_notes = state.get("safety_notes", [])

    # Build response
    response = f"# 💪 个性化运动方案\n\n"

    # User profile summary
    level_text = {
        "beginner": "初学者",
        "intermediate": "中级",
        "advanced": "高级",
    }.get(fitness_level, "初学者")

    response += f"**运动水平：**{level_text}\n\n"

    if fitness_goals:
        response += f"**运动目标：**{', '.join(fitness_goals)}\n\n"

    # Workout plan summary
    if workout_plan:
        response += "## 📋 训练计划概要\n\n"
        response += f"• **训练类型：**{workout_plan.get('plan_type', '综合训练')}\n"
        response += f"• **总时长：**{workout_plan.get('total_duration', 30)}分钟\n"
        response += f"• **动作数量：**{len(exercises)}个\n\n"

        response += "**训练结构：**\n"
        response += f"1. 热身：{workout_plan.get('warmup_duration', 5)}分钟\n"
        response += f"2. 正式训练：{workout_plan.get('main_duration', 20)}分钟\n"
        response += f"3. 放松拉伸：{workout_plan.get('cooldown_duration', 5)}分钟\n\n"

    # Exercise details
    if exercises:
        response += "## 🏃 具体动作\n\n"

        for i, ex in enumerate(exercises, 1):
            ex_type = ex.get("type", "exercise")
            type_emoji = {"cardio": "🏃", "strength": "💪", "flexibility": "🧘"}.get(ex_type, "🏃")

            response += f"### {i}. {type_emoji} {ex.get('name', '未知动作')}\n\n"
            response += f"**类型：**{ex_type}\n"
            response += f"**时长：**{ex.get('duration', 0)}分钟\n"
            response += f"**强度：**{ex.get('intensity', '中')}\n"

            if ex.get('sets'):
                response += f"**组数：**{ex.get('sets')}组\n"

            response += f"\n**说明：**{ex.get('description', '')}\n\n"

    # Safety notes
    if safety_notes:
        response += "## ⚠️ 安全提示\n\n"
        for note in safety_notes:
            response += f"• {note}\n"
        response += "\n"

    # Footer
    response += "---\n\n"
    response += "*💡 提示：请根据自身身体状况调整运动强度，循序渐进。如有不适，请立即停止运动并咨询医生。*\n"

    state["response"] = response

    logger.info(f"[format_response] Response formatted: {len(response)} characters")

    return state
