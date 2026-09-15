"""Exercise planning tools used by ExerciseAgent nodes."""

from __future__ import annotations

from typing import Any

from app.tools.registry import tool_registry


EXERCISE_DB = {
    "cardio": {
        "beginner": [
            {"name": "快走", "duration": 20, "intensity": "低", "description": "保持舒适速度的快步行走"},
            {"name": "原地慢跑", "duration": 10, "intensity": "低", "description": "原地轻松慢跑"},
            {"name": "开合跳", "duration": 5, "intensity": "中", "description": "每组30秒，间歇休息", "sets": 3},
        ],
        "intermediate": [
            {"name": "慢跑", "duration": 30, "intensity": "中", "description": "保持可以说话的配速"},
            {"name": "跳绳", "duration": 10, "intensity": "高", "description": "分组进行，每组2分钟"},
            {"name": "高抬腿", "duration": 5, "intensity": "高", "description": "每组45秒，间歇15秒", "sets": 3},
        ],
        "advanced": [
            {"name": "跑步", "duration": 45, "intensity": "高", "description": "间歇跑或配速跑"},
            {"name": "波比跳", "duration": 10, "intensity": "极高", "description": "每组10-15个", "sets": 3},
            {"name": "登山者", "duration": 5, "intensity": "高", "description": "每组45秒", "sets": 3},
        ],
    },
    "strength": {
        "beginner": [
            {"name": "墙壁俯卧撑", "duration": 10, "intensity": "低", "description": "双手撑墙，进行俯卧撑动作"},
            {"name": "徒手深蹲", "duration": 10, "intensity": "低", "description": "注意膝盖不超过脚尖"},
            {"name": "平板支撑", "duration": 3, "intensity": "中", "description": "保持核心收紧，量力而行", "sets": 2},
        ],
        "intermediate": [
            {"name": "俯卧撑", "duration": 10, "intensity": "中", "description": "标准俯卧撑，注意身体保持直线"},
            {"name": "深蹲", "duration": 10, "intensity": "中", "description": "可以手持重物增加强度"},
            {"name": "弓步蹲", "duration": 10, "intensity": "中", "description": "左右交替进行"},
            {"name": "平板支撑", "duration": 5, "intensity": "中", "description": "保持标准姿势"},
        ],
        "advanced": [
            {"name": "钻石俯卧撑", "duration": 10, "intensity": "高", "description": "双手呈钻石形状，重点锻炼三头肌"},
            {"name": "单腿深蹲", "duration": 10, "intensity": "高", "description": "单腿进行深蹲，需要很好平衡"},
            {"name": "倒立撑", "duration": 10, "intensity": "极高", "description": "靠墙倒立进行俯卧撑"},
            {"name": "负重平板支撑", "duration": 5, "intensity": "高", "description": "背部放置重物进行平板支撑"},
        ],
    },
    "flexibility": {
        "beginner": [
            {"name": "颈部拉伸", "duration": 3, "intensity": "低", "description": "缓慢转动和倾斜颈部"},
            {"name": "肩部拉伸", "duration": 3, "intensity": "低", "description": "手臂交叉拉伸肩部"},
            {"name": "腿部拉伸", "duration": 5, "intensity": "低", "description": "坐姿前屈拉伸腿部后侧"},
            {"name": "全身放松", "duration": 5, "intensity": "低", "description": "躺下放松全身肌肉"},
        ],
        "intermediate": [
            {"name": "瑜伽拜日式", "duration": 10, "intensity": "中", "description": "按流程完成拜日式序列"},
            {"name": "深度拉伸", "duration": 10, "intensity": "中", "description": "每个动作保持30-60秒"},
            {"name": "平衡练习", "duration": 5, "intensity": "中", "description": "单腿站立等平衡动作"},
        ],
        "advanced": [
            {"name": "高强度瑜伽", "duration": 15, "intensity": "高", "description": "流瑜伽或力量瑜伽"},
            {"name": "极限拉伸", "duration": 10, "intensity": "高", "description": "达到极限位置的深度拉伸"},
            {"name": "冥想放松", "duration": 10, "intensity": "低", "description": "配合冥想的全身放松"},
        ],
    },
}


def generate_exercise_plan_tool(
    fitness_level: str,
    fitness_goals: list[str],
    health_conditions: list[str] | None = None,
    time_available: int = 30,
) -> dict[str, Any]:
    """Generate a deterministic baseline exercise plan."""
    health_conditions = health_conditions or []
    workout_type = "cardio"
    if "增肌" in fitness_goals or "力量" in fitness_goals:
        workout_type = "strength"
    elif "柔韧" in fitness_goals or "瑜伽" in fitness_goals:
        workout_type = "flexibility"
    elif any(goal in fitness_goals for goal in ["减脂", "减肥", "耐力", "心肺"]):
        workout_type = "cardio"
    elif "健康" in fitness_goals:
        workout_type = "mixed"

    exercises: list[dict[str, Any]] = []
    if workout_type == "mixed":
        for type_name in ("cardio", "strength", "flexibility"):
            candidates = EXERCISE_DB[type_name].get(fitness_level, [])
            if candidates:
                exercises.append({**candidates[0], "type": type_name})
    else:
        candidates = EXERCISE_DB.get(workout_type, {}).get(fitness_level, [])
        if time_available <= 20:
            exercises = candidates[:2]
        elif time_available <= 45:
            exercises = candidates[:4]
        else:
            exercises = list(candidates)
        exercises = [{**item, "type": workout_type} for item in exercises]

    safety_notes: list[str] = []
    if health_conditions:
        safety_notes.append("请根据个人健康状况调整运动强度，如有不适请立即停止")
        if any(condition in ["心脏病", "高血压"] for condition in health_conditions):
            safety_notes.append("心血管疾病患者应避免剧烈运动，监测心率")
        if "糖尿病" in health_conditions:
            safety_notes.append("糖尿病患者运动前后注意监测血糖，随身携带糖果")
        if any(condition in ["膝盖", "关节", "腰间盘"] for condition in health_conditions):
            safety_notes.append("关节问题患者避免跳跃和负重动作，选择低冲击运动")
        if "哮喘" in health_conditions:
            safety_notes.append("哮喘患者应避免寒冷干燥环境下的户外运动，随身携带药物")

    if fitness_level == "beginner":
        safety_notes.extend(["初学者应循序渐进，从低强度开始，逐步增加运动量", "运动前充分热身5-10分钟，运动后拉伸放松"])
    elif fitness_level == "intermediate":
        safety_notes.append("注意运动后的恢复，保证充足睡眠")
    elif fitness_level == "advanced":
        safety_notes.append("高强度训练时注意监测身体反应，避免过度训练")

    return {
        "workout_plan": {
            "plan_type": workout_type,
            "fitness_level": fitness_level,
            "goals": fitness_goals,
            "total_duration": time_available,
            "exercise_count": len(exercises),
            "warmup_duration": 5 if fitness_level != "advanced" else 10,
            "main_duration": time_available - 10,
            "cooldown_duration": 5,
            "data_source": "local_exercise_tool",
        },
        "exercises": exercises,
        "safety_notes": safety_notes,
    }


tool_registry.register(
    "generate_exercise_plan",
    "Generate a deterministic baseline exercise plan from user goals and constraints.",
    generate_exercise_plan_tool,
    {
        "type": "object",
        "properties": {
            "fitness_level": {"type": "string"},
            "fitness_goals": {"type": "array", "items": {"type": "string"}},
            "health_conditions": {"type": "array", "items": {"type": "string"}},
            "time_available": {"type": "integer"},
        },
        "required": ["fitness_level", "fitness_goals"],
    },
)
