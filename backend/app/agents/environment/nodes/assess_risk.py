"""Assess health risks based on environmental data."""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


def calculate_heat_stress_risk(temperature: float, humidity: int) -> tuple:
    """Calculate heat stress risk level.

    Uses simplified heat index calculation.

    Args:
        temperature: Temperature in Celsius
        humidity: Relative humidity percentage

    Returns:
        (risk_level, description)
    """
    # Simplified heat index
    # Real heat index formula is more complex
    hi = temperature + (humidity / 100) * 5

    if hi < 27:
        return "low", "热应激风险低"
    elif hi < 32:
        return "moderate", "热应激风险中等，建议适当补水"
    elif hi < 41:
        return "high", "热应激风险高，避免剧烈运动，多饮水"
    else:
        return "very_high", "热应激风险极高，避免户外活动"


def calculate_cold_stress_risk(temperature: float, wind_speed: float) -> tuple:
    """Calculate cold stress risk level.

    Args:
        temperature: Temperature in Celsius
        wind_speed: Wind speed in m/s

    Returns:
        (risk_level, description)
    """
    # Wind chill approximation
    if temperature > 10:
        return "low", "低温风险低"

    wc = 13.12 + 0.6215 * temperature - 11.37 * (wind_speed * 3.6)**0.16 + 0.3965 * temperature * (wind_speed * 3.6)**0.16

    if wc > -10:
        return "low", "低温风险低"
    elif wc > -25:
        return "moderate", "低温风险中等，注意保暖"
    elif wc > -35:
        return "high", "低温风险高，做好防寒措施"
    else:
        return "very_high", "低温风险极高，避免户外活动"


def calculate_uv_risk(uv_index: int) -> tuple:
    """Calculate UV risk level.

    Args:
        uv_index: UV index value

    Returns:
        (risk_level, description, protection_advice)
    """
    if uv_index <= 2:
        return "low", "紫外线风险低", "无需特别防护"
    elif uv_index <= 5:
        return "moderate", "紫外线风险中等", "建议涂抹防晒霜，戴帽子"
    elif uv_index <= 7:
        return "high", "紫外线风险高", "必须涂抹防晒霜(SPF30+)，戴帽子和太阳镜"
    elif uv_index <= 10:
        return "very_high", "紫外线风险极高", "避免10:00-16:00户外活动，全面防护"
    else:
        return "extreme", "紫外线风险极端", "避免户外活动，必须外出时全面防护"


def assess_air_quality_risk(aqi: int, pm25: float) -> tuple:
    """Assess air quality health risk.

    Args:
        aqi: Air Quality Index
        pm25: PM2.5 concentration

    Returns:
        (risk_level, affected_groups, advice)
    """
    if aqi <= 50:
        return "low", [], "空气质量优良，适宜户外活动"
    elif aqi <= 100:
        return "moderate", ["极少数异常敏感人群"], "空气质量良好，敏感人群应减少户外活动"
    elif aqi <= 150:
        return "high", ["儿童", "老年人", "心脏病患者", "呼吸系统疾病患者"], "不健康，敏感人群应避免户外活动，一般人群减少户外活动"
    elif aqi <= 200:
        return "very_high", ["所有人"], "很不健康，所有人应避免户外活动，敏感人群应留在室内"
    elif aqi <= 300:
        return "severe", ["所有人"], "危险，所有人应留在室内，避免户外活动"
    else:
        return "hazardous", ["所有人"], "有毒害，所有人必须留在室内，开启空气净化器"


def assess_risk(state: Dict[str, Any]) -> Dict[str, Any]:
    """Assess health risks based on environmental data.

    Analyzes weather, air quality, and other environmental factors
    to determine health risks and provide warnings.

    Args:
        state: Current state with weather and air quality data

    Returns:
        Updated state with health risk assessment
    """
    logger.info("[assess_risk] Assessing health risks")

    weather = state.get("weather")
    air_quality = state.get("air_quality")
    location = state.get("location", {})

    if not weather and not air_quality:
        logger.warning("[assess_risk] No environmental data available")
        state["error"] = "无法获取环境数据，无法评估健康风险"
        return state

    # Calculate various risk levels
    risks = {
        "overall_risk": "low",
        "air_quality_risk": "low",
        "weather_risk": "low",
        "heat_stress_risk": "low",
        "cold_stress_risk": "low",
        "uv_risk": "low",
        "allergen_risk": "low",
    }

    warnings = []
    precautions = []
    sensitive_groups = []

    # Assess air quality risk
    if air_quality:
        aqi = air_quality.get("aqi", 0)
        pm25 = air_quality.get("pm25", 0)

        aq_risk, affected_groups, advice = assess_air_quality_risk(aqi, pm25)
        risks["air_quality_risk"] = aq_risk

        if affected_groups:
            sensitive_groups.extend(affected_groups)

        if aq_risk in ["high", "very_high", "severe", "hazardous"]:
            warnings.append(f"空气质量{aq_risk}：{advice}")
            precautions.append("外出时佩戴N95口罩")
            precautions.append("关闭门窗，开启空气净化器")

    # Assess weather risks
    if weather:
        temp = weather.get("temperature", 20)
        humidity = weather.get("humidity", 50)
        wind_speed = weather.get("wind_speed", 5)
        uv_index = weather.get("uv_index", 5)

        # Heat stress
        heat_risk, heat_desc = calculate_heat_stress_risk(temp, humidity)
        risks["heat_stress_risk"] = heat_risk

        if heat_risk in ["high", "very_high"]:
            warnings.append(f"高温预警：{heat_desc}")
            precautions.append("避免高温时段户外活动")
            precautions.append("多喝水，补充电解质")
            sensitive_groups.extend(["儿童", "老年人", "户外工作者"])

        # Cold stress
        cold_risk, cold_desc = calculate_cold_stress_risk(temp, wind_speed)
        risks["cold_stress_risk"] = cold_risk

        if cold_risk in ["high", "very_high"]:
            warnings.append(f"低温预警：{cold_desc}")
            precautions.append("穿戴保暖衣物")
            precautions.append("注意面部和四肢保暖")
            sensitive_groups.extend(["老年人", "心血管疾病患者"])

        # UV risk
        uv_risk, uv_desc, uv_advice = calculate_uv_risk(uv_index)
        risks["uv_risk"] = uv_risk

        if uv_risk in ["high", "very_high", "extreme"]:
            warnings.append(f"紫外线预警：{uv_desc}")
            precautions.append(uv_advice)
            sensitive_groups.append("皮肤敏感人群")

    # Determine overall risk
    risk_levels = ["low", "moderate", "high", "very_high", "severe", "hazardous"]
    max_risk_level = 0
    for risk_type, risk_value in risks.items():
        if risk_type != "overall_risk" and risk_value in risk_levels:
            level_index = risk_levels.index(risk_value)
            max_risk_level = max(max_risk_level, level_index)

    risks["overall_risk"] = risk_levels[max_risk_level]

    # Remove duplicates from sensitive groups
    sensitive_groups = list(set(sensitive_groups))

    # Build health risk assessment
    health_risk = {
        "overall_risk": risks["overall_risk"],
        "air_quality_risk": risks["air_quality_risk"],
        "weather_risk": risks["weather_risk"] if weather else "unknown",
        "heat_stress_risk": risks["heat_stress_risk"],
        "cold_stress_risk": risks["cold_stress_risk"],
        "uv_risk": risks["uv_risk"],
        "allergen_risk": "low",  # TODO: Add pollen/ allergen data
        "sensitive_groups": sensitive_groups,
        "warnings": warnings,
        "precautions": precautions,
    }

    state["health_risk"] = health_risk

    logger.info(f"[assess_risk] Overall risk: {risks['overall_risk']}, "
                f"Warnings: {len(warnings)}, Precautions: {len(precautions)}")

    return state
