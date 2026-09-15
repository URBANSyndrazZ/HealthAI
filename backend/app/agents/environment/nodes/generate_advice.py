"""Generate personalized environmental health advice."""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def get_activity_recommendations(
    air_quality: Dict[str, Any],
    weather: Dict[str, Any],
    health_risk: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Generate outdoor activity recommendations."""
    recommendations = []

    overall_risk = health_risk.get("overall_risk", "low")
    aqi = air_quality.get("aqi", 0) if air_quality else 0

    # Outdoor exercise recommendation
    if overall_risk == "low" and aqi <= 50:
        recommendations.append({
            "category": "outdoor_activity",
            "priority": "low",
            "title": "适宜户外活动",
            "description": "当前环境条件良好，非常适合户外活动和运动。",
            "action_items": [
                "可进行跑步、骑行等有氧运动",
                "建议在公园、绿地等空气质量好的地方活动",
                "注意防晒和补水"
            ],
            "best_time": "早晨6:00-8:00或傍晚17:00-19:00",
            "avoid_time": None,
        })
    elif overall_risk in ["low", "moderate"] and aqi <= 100:
        recommendations.append({
            "category": "outdoor_activity",
            "priority": "medium",
            "title": "适度户外活动",
            "description": "当前环境条件一般，可以进行轻度户外活动。",
            "action_items": [
                "适合散步、太极等轻度运动",
                "避免剧烈运动",
                "敏感人群应减少户外时间"
            ],
            "best_time": "上午9:00-10:00或下午15:00-16:00",
            "avoid_time": "交通高峰期",
        })
    else:
        recommendations.append({
            "category": "outdoor_activity",
            "priority": "high",
            "title": "减少户外活动",
            "description": "当前环境条件较差，建议减少户外活动。",
            "action_items": [
                "避免户外活动，留在室内",
                "如需外出，佩戴防护口罩",
                "关闭门窗，开启空气净化器"
            ],
            "best_time": None,
            "avoid_time": "全天",
        })

    return recommendations


def get_health_protection_recommendations(
    air_quality: Dict[str, Any],
    weather: Dict[str, Any],
    health_risk: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Generate health protection recommendations."""
    recommendations = []

    uv_risk = health_risk.get("uv_risk", "low")
    uv_index = weather.get("uv_index", 0) if weather else 0

    # UV protection
    if uv_risk in ["high", "very_high", "extreme"]:
        recommendations.append({
            "category": "health_protection",
            "priority": "high" if uv_risk == "extreme" else "medium",
            "title": "紫外线防护",
            "description": f"紫外线指数{uv_index}（{uv_risk}），需要做好防护措施。",
            "action_items": [
                "涂抹SPF30+防晒霜",
                "佩戴太阳镜和遮阳帽",
                "穿长袖衣物",
                "避免10:00-16:00强烈日晒"
            ],
            "best_time": "早晨或傍晚",
            "avoid_time": "10:00-16:00",
        })

    # Air quality protection
    aqi = air_quality.get("aqi", 0) if air_quality else 0
    if aqi > 100:
        recommendations.append({
            "category": "health_protection",
            "priority": "high" if aqi > 150 else "medium",
            "title": "空气质量防护",
            "description": f"AQI为{aqi}，空气质量较差，需要采取防护措施。",
            "action_items": [
                "外出佩戴N95口罩",
                "关闭门窗，开启空气净化器",
                "减少户外活动时间",
                "敏感人群应留在室内"
            ],
            "best_time": None,
            "avoid_time": "全天",
        })

    # Weather-related protection
    temp = weather.get("temperature", 20) if weather else 20
    if temp > 35:
        recommendations.append({
            "category": "health_protection",
            "priority": "high",
            "title": "高温防暑",
            "description": f"气温高达{temp}°C，注意防暑降温。",
            "action_items": [
                "多喝水，补充电解质",
                "避免高温时段户外活动",
                "穿着透气轻薄衣物",
                "注意室内降温"
            ],
            "best_time": "早晨或傍晚",
            "avoid_time": "11:00-15:00",
        })
    elif temp < 5:
        recommendations.append({
            "category": "health_protection",
            "priority": "high",
            "title": "低温防寒",
            "description": f"气温低至{temp}°C，注意保暖防寒。",
            "action_items": [
                "穿着保暖衣物，注意头部和手脚保暖",
                "减少户外暴露时间",
                "保持室内温暖",
                "注意心脑血管保护"
            ],
            "best_time": "中午时段",
            "avoid_time": "早晚低温时段",
        })

    return recommendations


def get_indoor_air_recommendations(
    air_quality: Dict[str, Any],
    health_risk: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """Generate indoor air quality recommendations."""
    recommendations = []

    aqi = air_quality.get("aqi", 0) if air_quality else 0
    pm25 = air_quality.get("pm25", 0) if air_quality else 0

    if aqi > 100 or pm25 > 75:
        recommendations.append({
            "category": "indoor_air",
            "priority": "high" if aqi > 150 else "medium",
            "title": "室内空气优化",
            "description": "室外空气质量差，需要优化室内空气环境。",
            "action_items": [
                "关闭门窗，防止室外污染物进入",
                "开启空气净化器，调至最大档",
                "使用新风系统的，检查滤芯并开启",
                "可适当使用绿植辅助净化空气"
            ],
            "best_time": None,
            "avoid_time": None,
        })

    return recommendations


def generate_advice(state: Dict[str, Any]) -> Dict[str, Any]:
    """Generate personalized environmental health advice.

    Creates recommendations based on:
    - Air quality conditions
    - Weather conditions
    - Health risk assessment

    Args:
        state: Current state with environmental data

    Returns:
        Updated state with recommendations
    """
    logger.info("[generate_advice] Generating health recommendations")

    air_quality = state.get("air_quality")
    weather = state.get("weather")
    health_risk = state.get("health_risk")

    recommendations = []

    # Generate activity recommendations
    if air_quality or weather:
        recommendations.extend(get_activity_recommendations(
            air_quality or {}, weather or {}, health_risk or {}
        ))

    # Generate health protection recommendations
        recommendations.extend(get_health_protection_recommendations(
            air_quality or {}, weather or {}, health_risk or {}
        ))

    # Generate indoor air recommendations
    if air_quality:
        recommendations.extend(get_indoor_air_recommendations(
            air_quality, health_risk or {}
        ))

    # Sort by priority
    priority_order = {"high": 0, "medium": 1, "low": 2}
    recommendations.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 3))

    state["recommendations"] = recommendations

    logger.info(f"[generate_advice] Generated {len(recommendations)} recommendations")

    return state
