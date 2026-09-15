"""Format the final response for the Environment Agent."""

import logging
from typing import Dict, Any

from app.core.time import utc_now

logger = logging.getLogger(__name__)


def get_aqi_description(level: str) -> str:
    """Get Chinese description for AQI level."""
    descriptions = {
        "good": "优",
        "moderate": "良",
        "unhealthy_sensitive": "轻度污染",
        "unhealthy": "中度污染",
        "very_unhealthy": "重度污染",
        "hazardous": "严重污染",
    }
    return descriptions.get(level, "未知")


def format_air_quality_section(air_quality: Dict[str, Any]) -> str:
    """Format air quality section."""
    if not air_quality:
        return "❓ 无法获取空气质量数据\n"

    aqi = air_quality.get("aqi", 0)
    level = air_quality.get("level", "unknown")
    pm25 = air_quality.get("pm25", 0)
    pm10 = air_quality.get("pm10", 0)
    primary = air_quality.get("primary_pollutant", "PM2.5")

    level_desc = get_aqi_description(level)
    emoji = "🟢" if level == "good" else "🟡" if level == "moderate" else "🟠" if level in ["unhealthy_sensitive", "unhealthy"] else "🔴"

    section = f"{emoji} **空气质量：{level_desc} (AQI: {aqi})**\n\n"
    section += f"• PM2.5: {pm25} μg/m³\n"
    section += f"• PM10: {pm10} μg/m³\n"
    section += f"• 首要污染物: {primary}\n"

    return section


def format_weather_section(weather: Dict[str, Any]) -> str:
    """Format weather section."""
    if not weather:
        return "❓ 无法获取天气数据\n"

    temp = weather.get("temperature", 0)
    feels_like = weather.get("feels_like", 0)
    humidity = weather.get("humidity", 0)
    desc = weather.get("weather_description", "未知")
    wind_speed = weather.get("wind_speed", 0)
    wind_dir = weather.get("wind_direction", "")
    uv = weather.get("uv_index", 0)
    visibility = weather.get("visibility", 0)
    target_date = weather.get("target_date")
    temp_high = weather.get("temp_high")
    temp_low = weather.get("temp_low")
    precipitation = weather.get("precipitation_sum")
    source = weather.get("data_source")

    label = f"{target_date} 天气" if target_date else "当前天气"
    temp_line = f"{temp}°C"
    if temp_high is not None and temp_low is not None:
        temp_line = f"{temp_low}-{temp_high}°C，均温约{temp}°C"

    section = f"🌤️ **{label}：{desc} {temp_line}**\n\n"
    section += f"• 体感温度: {feels_like}°C\n"
    section += f"• 湿度: {humidity}%\n"
    section += f"• 风向风力: {wind_dir}风 {wind_speed} m/s\n"
    if precipitation is not None:
        section += f"• 降水量: {precipitation} mm\n"
    section += f"• 能见度: {visibility/1000:.1f} km\n"
    section += f"• 紫外线指数: {uv}\n"
    if source:
        section += f"• 数据来源: {source}\n"

    return section


def format_recommendations_section(recommendations: list) -> str:
    """Format recommendations section."""
    if not recommendations:
        return "暂无具体建议。\n"

    section = ""

    # Group by category
    categories = {
        "outdoor_activity": "🚶 户外活动建议",
        "health_protection": "🛡️ 健康防护建议",
        "indoor_air": "🏠 室内空气建议",
    }

    categorized = {}
    for rec in recommendations:
        cat = rec.get("category", "general")
        if cat not in categorized:
            categorized[cat] = []
        categorized[cat].append(rec)

    for cat_key, cat_title in categories.items():
        if cat_key in categorized:
            section += f"\n**{cat_title}**\n\n"
            for i, rec in enumerate(categorized[cat_key][:2], 1):  # Limit to 2 per category
                priority_emoji = "🔴" if rec.get("priority") == "high" else "🟡" if rec.get("priority") == "medium" else "🟢"
                section += f"{priority_emoji} **{rec.get('title', '建议')}**\n"
                section += f"{rec.get('description', '')}\n"

                action_items = rec.get("action_items", [])
                if action_items:
                    section += "\n建议措施：\n"
                    for action in action_items[:3]:  # Limit to 3 actions
                        section += f"• {action}\n"

                if rec.get("best_time"):
                    section += f"\n最佳时间：{rec['best_time']}\n"
                if rec.get("avoid_time"):
                    section += f"避免时间：{rec['avoid_time']}\n"

                section += "\n"

    return section


def format_response(state: Dict[str, Any]) -> Dict[str, Any]:
    """Format the final response for the user.

    Creates a comprehensive, user-friendly report including:
    - Location information
    - Air quality data and interpretation
    - Weather conditions
    - Health risk assessment
    - Personalized recommendations

    Args:
        state: Final state with all data

    Returns:
        Updated state with formatted response
    """
    logger.info("[format_response] Formatting final response")

    location = state.get("location", {})
    air_quality = state.get("air_quality")
    weather = state.get("weather")
    health_risk = state.get("health_risk")
    recommendations = state.get("recommendations", [])
    llm_advice = str(state.get("llm_advice") or "").strip()

    location_name = location.get("city", "未知地点")
    timestamp = utc_now().strftime("%Y年%m月%d日 %H:%M UTC")

    # Build response
    response = f"# 🌍 {location_name} 环境健康报告\n\n"
    response += f"*更新时间：{timestamp}*\n\n"

    # Health risk summary
    if health_risk:
        overall_risk = health_risk.get("overall_risk", "low")
        risk_emoji = {
            "low": "🟢",
            "moderate": "🟡",
            "high": "🟠",
            "very_high": "🔴",
            "severe": "🔴",
            "hazardous": "⚫",
        }.get(overall_risk, "🟢")

        risk_text = {
            "low": "低风险",
            "moderate": "中等风险",
            "high": "高风险",
            "very_high": "很高风险",
            "severe": "严重风险",
            "hazardous": "危险",
        }.get(overall_risk, "低风险")

        response += f"## {risk_emoji} 健康风险总评：{risk_text}\n\n"

        # Warnings
        warnings = health_risk.get("warnings", [])
        if warnings:
            response += "**⚠️ 健康预警：**\n"
            for warning in warnings[:5]:  # Limit to 5 warnings
                response += f"• {warning}\n"
            response += "\n"

        # Sensitive groups
        sensitive_groups = health_risk.get("sensitive_groups", [])
        if sensitive_groups:
            response += f"**👥 敏感人群：**{', '.join(list(set(sensitive_groups))[:10])}\n\n"

    if llm_advice:
        response += "---\n\n"
        response += "## 个性化解读\n\n"
        response += f"{llm_advice}\n\n"

    # Air quality section
    if air_quality:
        response += "---\n\n"
        response += "## 🫁 空气质量\n\n"
        response += format_air_quality_section(air_quality)
        response += "\n"

    # Weather section
    if weather:
        response += "---\n\n"
        response += "## 🌤️ 天气状况\n\n"
        response += format_weather_section(weather)
        response += "\n"

    # Recommendations section
    if recommendations:
        response += "---\n\n"
        response += "## 💡 健康建议\n\n"
        response += format_recommendations_section(recommendations)
        response += "\n"

    # Footer
    response += "---\n\n"
    response += "*💡 提示：本报告基于实时环境数据和当前天气条件生成，建议您根据实际情况调整活动计划。*\n"

    state["response"] = response

    logger.info(f"[format_response] Response formatted: {len(response)} characters")

    return state
