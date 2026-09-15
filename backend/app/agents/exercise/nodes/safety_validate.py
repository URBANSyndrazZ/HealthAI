"""Safety validation for exercise plans after rule or LLM generation."""

from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)

HIGH_INTENSITY = {"高", "极高", "very_high", "high"}
HIGH_IMPACT_NAMES = ("跳绳", "波比", "开合跳", "高抬腿", "冲刺", "间歇跑")


def _collect_conditions(state: dict[str, Any]) -> list[str]:
    conditions = [str(item) for item in state.get("health_conditions", [])]
    profile = state.get("user_profile") or {}
    if isinstance(profile, dict):
        for key in ("health_conditions", "chronic_diseases", "injuries"):
            value = profile.get(key)
            if isinstance(value, list):
                conditions.extend(str(item) for item in value)
        health_status = profile.get("health_status") or {}
        if isinstance(health_status, dict):
            for value in health_status.values():
                if isinstance(value, list):
                    conditions.extend(str(item) for item in value)
                elif value:
                    conditions.append(str(value))
    return list(dict.fromkeys(conditions))


def _environment_data(state: dict[str, Any]) -> dict[str, Any]:
    prior_results = state.get("prior_results") or {}
    if isinstance(state.get("environment_data"), dict):
        return state["environment_data"]
    if isinstance(prior_results, dict):
        if isinstance(prior_results.get("environment"), dict):
            return prior_results["environment"]
        if isinstance(prior_results.get("environment_analysis"), dict):
            return prior_results["environment_analysis"].get("result") or prior_results["environment_analysis"]
    return {}


def _replacement_exercise(reason: str) -> dict[str, Any]:
    return {
        "name": "固定自行车",
        "duration": 20,
        "intensity": "低",
        "description": reason,
        "type": "cardio",
    }


def safety_validate(state: dict[str, Any]) -> dict[str, Any]:
    """Apply deterministic safety guardrails to the exercise plan."""
    exercises = copy.deepcopy(state.get("exercises", []))
    notes = list(state.get("safety_notes", []))
    conditions = _collect_conditions(state)
    env = _environment_data(state)
    air_quality = env.get("air_quality") or {}
    weather = env.get("weather") or {}
    aqi = air_quality.get("aqi")
    temp = weather.get("temperature")
    uv_index = weather.get("uv_index")

    has_cardiovascular = any("高血压" in item or "心脏" in item for item in conditions)
    has_joint_issue = any("膝" in item or "关节" in item or "腰间盘" in item for item in conditions)

    validated: list[dict[str, Any]] = []
    for exercise in exercises:
        if not isinstance(exercise, dict):
            continue
        item = dict(exercise)
        name = str(item.get("name", ""))
        intensity = str(item.get("intensity", "中"))

        if state.get("fitness_level") == "beginner" and intensity in HIGH_INTENSITY:
            item["intensity"] = "中"
            notes.append("初学者计划已限制为中低强度，避免一开始训练过猛。")

        if has_cardiovascular and intensity in HIGH_INTENSITY:
            item["intensity"] = "低"
            notes.append("存在心血管相关风险时，避免高强度运动和憋气发力。")

        if has_joint_issue and any(keyword in name for keyword in HIGH_IMPACT_NAMES):
            item = _replacement_exercise("已因关节/膝盖风险替换高冲击动作，建议选择低冲击有氧。")
            notes.append("存在关节相关风险时，避免跳跃、冲刺等高冲击动作。")

        validated.append(item)

    if aqi is not None:
        try:
            aqi_value = float(aqi)
            if aqi_value > 150:
                state["location"] = "indoor"
                notes.append("当前空气质量较差，不建议户外跑步，已按室内运动处理。")
            elif aqi_value > 100:
                notes.append("空气质量一般，户外运动应缩短时长并降低强度。")
        except (TypeError, ValueError):
            pass

    if temp is not None:
        try:
            temp_value = float(temp)
            if temp_value > 35:
                notes.append("高温天气避免中午户外运动，优先选择清晨、傍晚或室内。")
            elif temp_value < 0:
                notes.append("低温天气注意充分热身和保暖，必要时改为室内运动。")
        except (TypeError, ValueError):
            pass

    if uv_index is not None:
        try:
            if float(uv_index) >= 7:
                notes.append("紫外线较强，户外运动应避开10:00-16:00并做好防晒。")
        except (TypeError, ValueError):
            pass

    state["exercises"] = validated
    state["safety_notes"] = list(dict.fromkeys(str(note) for note in notes if str(note).strip()))
    state["safety_validation_status"] = "completed"
    logger.info("[safety_validate] Validated %d exercise items", len(validated))
    return state
