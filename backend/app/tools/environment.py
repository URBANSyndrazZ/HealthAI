import logging
import random
import re
from datetime import date, timedelta
from typing import Any

import httpx

from app.core.time import utc_isoformat, utc_now
from app.tools.registry import tool_registry

logger = logging.getLogger(__name__)

CITY_DATABASE = {
    "北京": {"city": "北京市", "country": "中国", "lat": 39.9042, "lon": 116.4074, "timezone": "Asia/Shanghai"},
    "beijing": {"city": "北京市", "country": "中国", "lat": 39.9042, "lon": 116.4074, "timezone": "Asia/Shanghai"},
    "上海": {"city": "上海市", "country": "中国", "lat": 31.2304, "lon": 121.4737, "timezone": "Asia/Shanghai"},
    "shanghai": {"city": "上海市", "country": "中国", "lat": 31.2304, "lon": 121.4737, "timezone": "Asia/Shanghai"},
    "广州": {"city": "广州市", "country": "中国", "lat": 23.1291, "lon": 113.2644, "timezone": "Asia/Shanghai"},
    "guangzhou": {"city": "广州市", "country": "中国", "lat": 23.1291, "lon": 113.2644, "timezone": "Asia/Shanghai"},
    "深圳": {"city": "深圳市", "country": "中国", "lat": 22.5431, "lon": 114.0579, "timezone": "Asia/Shanghai"},
    "shenzhen": {"city": "深圳市", "country": "中国", "lat": 22.5431, "lon": 114.0579, "timezone": "Asia/Shanghai"},
    "杭州": {"city": "杭州市", "country": "中国", "lat": 30.2741, "lon": 120.1551, "timezone": "Asia/Shanghai"},
    "hangzhou": {"city": "杭州市", "country": "中国", "lat": 30.2741, "lon": 120.1551, "timezone": "Asia/Shanghai"},
    "成都": {"city": "成都市", "country": "中国", "lat": 30.5728, "lon": 104.0668, "timezone": "Asia/Shanghai"},
    "chengdu": {"city": "成都市", "country": "中国", "lat": 30.5728, "lon": 104.0668, "timezone": "Asia/Shanghai"},
    "西安": {"city": "西安市", "country": "中国", "lat": 34.3416, "lon": 108.9398, "timezone": "Asia/Shanghai"},
    "xian": {"city": "西安市", "country": "中国", "lat": 34.3416, "lon": 108.9398, "timezone": "Asia/Shanghai"},
    "武汉": {"city": "武汉市", "country": "中国", "lat": 30.5928, "lon": 114.3055, "timezone": "Asia/Shanghai"},
    "wuhan": {"city": "武汉市", "country": "中国", "lat": 30.5928, "lon": 114.3055, "timezone": "Asia/Shanghai"},
    "南京": {"city": "南京市", "country": "中国", "lat": 32.0603, "lon": 118.7969, "timezone": "Asia/Shanghai"},
    "nanjing": {"city": "南京市", "country": "中国", "lat": 32.0603, "lon": 118.7969, "timezone": "Asia/Shanghai"},
    "重庆": {"city": "重庆市", "country": "中国", "lat": 29.5630, "lon": 106.5516, "timezone": "Asia/Shanghai"},
    "chongqing": {"city": "重庆市", "country": "中国", "lat": 29.5630, "lon": 106.5516, "timezone": "Asia/Shanghai"},
}

WEATHER_DESCRIPTIONS = {
    0: "晴朗",
    1: "大部晴朗",
    2: "局部多云",
    3: "阴天",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "毛毛雨",
    55: "强毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    80: "短时小阵雨",
    81: "阵雨",
    82: "强阵雨",
    95: "雷阵雨",
    96: "雷阵雨伴小冰雹",
    99: "雷阵雨伴强冰雹",
}

def resolve_location_tool(query: str) -> dict[str, Any]:
    """Resolve a city from free text, falling back to Beijing."""
    query_lower = (query or "").lower()
    for city_key, city_info in CITY_DATABASE.items():
        if city_key in query_lower:
            return city_info.copy()
    return CITY_DATABASE["北京"].copy()

def get_aqi_level(aqi: int) -> str:
    if aqi <= 50:
        return "good"
    if aqi <= 100:
        return "moderate"
    if aqi <= 150:
        return "unhealthy_sensitive"
    if aqi <= 200:
        return "unhealthy"
    if aqi <= 300:
        return "very_unhealthy"
    return "hazardous"

def get_primary_pollutant(pm25: float, pm10: float, o3: float) -> str:
    pollutants = [("PM2.5", pm25 * 2), ("PM10", pm10), ("O3", o3)]
    return max(pollutants, key=lambda x: x[1])[0]

def fetch_air_quality_tool(location: dict[str, Any]) -> dict[str, Any]:
    """Return air quality data for a resolved location."""
    city = location.get("city", "")
    tier1_cities = ["北京市", "上海市", "广州市", "深圳市"]
    base_aqi = random.randint(40, 120) if city in tier1_cities else random.randint(30, 150)

    hour = utc_now().hour
    if 8 <= hour <= 10 or 17 <= hour <= 19:
        base_aqi = int(base_aqi * 1.2)

    pm25 = round(base_aqi * random.uniform(0.5, 0.8), 1)
    pm10 = round(pm25 * random.uniform(1.5, 2.5), 1)
    o3 = round(random.uniform(40, 120), 1)
    no2 = round(random.uniform(20, 80), 1)
    so2 = round(random.uniform(5, 30), 1)
    co = round(random.uniform(0.5, 2.0), 2)

    return {
        "aqi": base_aqi,
        "pm25": pm25,
        "pm10": pm10,
        "o3": o3,
        "no2": no2,
        "so2": so2,
        "co": co,
        "level": get_aqi_level(base_aqi),
        "primary_pollutant": get_primary_pollutant(pm25, pm10, o3),
        "timestamp": utc_isoformat(),
        "data_source": "mock_air_quality_tool",
    }

def get_weather_desc(code: int) -> str:
    return WEATHER_DESCRIPTIONS.get(code, "多云")

def _wind_direction(degrees: float | int | None) -> str:
    if degrees is None:
        return ""
    directions = ["北", "东北", "东", "东南", "南", "西南", "西", "西北"]
    return directions[int((float(degrees) + 22.5) // 45) % 8]

def _target_date_from_message(message: str) -> date:
    today = utc_now().date()
    if "明天" in message:
        return today + timedelta(days=1)
    if "昨天" in message:
        return today - timedelta(days=1)
    if "今天" in message:
        return today

    iso_match = re.search(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?", message)
    if iso_match:
        year, month, day = map(int, iso_match.groups())
        return date(year, month, day)

    zh_match = re.search(r"(\d{1,2})月(\d{1,2})日", message)
    if zh_match:
        month, day = map(int, zh_match.groups())
        target = date(today.year, month, day)
        if target < today - timedelta(days=180):
            target = date(today.year + 1, month, day)
        return target

    dot_match = re.search(r"(\d{1,2})\.(\d{1,2})日?", message)
    if dot_match:
        month, day = map(int, dot_match.groups())
        target = date(today.year, month, day)
        if target < today - timedelta(days=180):
            target = date(today.year + 1, month, day)
        return target

    return today

def _daily_value(daily: dict[str, Any], key: str, default: Any = None) -> Any:
    values = daily.get(key) or []
    return values[0] if values else default


def _mean(values: list[float | int | None], default: float = 0) -> float:
    valid = [float(value) for value in values if value is not None]
    return sum(valid) / len(valid) if valid else default


def _build_weather_from_open_meteo(data: dict[str, Any], target_date: date, *, source: str) -> dict[str, Any]:
    daily = data.get("daily") or {}
    hourly = data.get("hourly") or {}
    temp_high = _daily_value(daily, "temperature_2m_max", 0)
    temp_low = _daily_value(daily, "temperature_2m_min", temp_high)
    feels_high = _daily_value(daily, "apparent_temperature_max", temp_high)
    feels_low = _daily_value(daily, "apparent_temperature_min", temp_low)
    weather_code = int(_daily_value(daily, "weather_code", 3) or 3)
    wind_speed = _daily_value(daily, "wind_speed_10m_max", 0)
    wind_dir = _wind_direction(_daily_value(daily, "wind_direction_10m_dominant"))
    humidity = round(_mean(hourly.get("relative_humidity_2m") or [], 60))
    visibility = round(_mean(hourly.get("visibility") or [], 10000))
    pressure = round(_mean(hourly.get("surface_pressure") or [], 1013))
    precipitation = float(_daily_value(daily, "precipitation_sum", 0) or 0)
    precipitation_probability = _daily_value(daily, "precipitation_probability_max")
    uv_index = round(float(_daily_value(daily, "uv_index_max", 0) or 0))
    avg_temp = round((float(temp_high or 0) + float(temp_low or 0)) / 2, 1)
    avg_feels = round((float(feels_high or avg_temp) + float(feels_low or avg_temp)) / 2, 1)

    return {
        "temperature": avg_temp,
        "temp_high": temp_high,
        "temp_low": temp_low,
        "feels_like": avg_feels,
        "humidity": humidity,
        "pressure": pressure,
        "wind_speed": wind_speed,
        "wind_direction": wind_dir,
        "visibility": visibility,
        "uv_index": uv_index,
        "weather_code": weather_code,
        "weather_description": get_weather_desc(weather_code),
        "precipitation_sum": precipitation,
        "precipitation_probability": precipitation_probability,
        "target_date": target_date.isoformat(),
        "data_source": source,
        "timestamp": utc_isoformat(),
    }


def _fetch_open_meteo_weather(location: dict[str, Any], target_date: date) -> dict[str, Any]:
    today = utc_now().date()
    is_historical = target_date < today
    endpoint = "https://archive-api.open-meteo.com/v1/archive" if is_historical else "https://api.open-meteo.com/v1/forecast"
    daily_vars = [
        "weather_code",
        "temperature_2m_max",
        "temperature_2m_min",
        "apparent_temperature_max",
        "apparent_temperature_min",
        "precipitation_sum",
        "wind_speed_10m_max",
        "wind_direction_10m_dominant",
    ]
    if not is_historical:
        daily_vars.extend(["uv_index_max", "precipitation_probability_max"])

    params = {
        "latitude": location.get("lat"),
        "longitude": location.get("lon"),
        "timezone": location.get("timezone") or "Asia/Shanghai",
        "start_date": target_date.isoformat(),
        "end_date": target_date.isoformat(),
        "daily": ",".join(daily_vars),
        "hourly": "relative_humidity_2m,surface_pressure,visibility",
        "temperature_unit": "celsius",
        "wind_speed_unit": "ms",
        "precipitation_unit": "mm",
    }
    with httpx.Client(timeout=8.0) as client:
        response = client.get(endpoint, params=params)
        response.raise_for_status()
        data = response.json()
    source = "Open-Meteo Historical Weather API" if is_historical else "Open-Meteo Forecast API"
    return _build_weather_from_open_meteo(data, target_date, source=source)

def _mock_weather(location: dict[str, Any], target_date: date) -> dict[str, Any]:
    city = location.get("city", "")
    base_temp = 15.0
    if "北京" in city or "西安" in city:
        base_temp = random.uniform(10, 20)
    elif "广州" in city or "深圳" in city:
        base_temp = random.uniform(22, 30)
    elif "上海" in city or "杭州" in city:
        base_temp = random.uniform(15, 25)
    elif "成都" in city or "重庆" in city:
        base_temp = random.uniform(16, 24)

    weather_code = random.randint(0, 5)
    temp = round(base_temp + random.uniform(-2, 2), 1)
    return {
        "temperature": temp,
        "feels_like": round(temp + random.uniform(-3, 3), 1),
        "humidity": random.randint(40, 85),
        "pressure": random.randint(1000, 1025),
        "wind_speed": round(random.uniform(1, 15), 1),
        "wind_direction": random.choice(["北", "东北", "东", "东南", "南", "西南", "西", "西北"]),
        "visibility": random.randint(8000, 20000),
        "uv_index": random.randint(1, 10),
        "weather_code": weather_code,
        "weather_description": get_weather_desc(weather_code),
        "precipitation_probability": random.randint(0, 60),
        "target_date": target_date.isoformat(),
        "data_source": "mock_weather_fallback",
        "timestamp": utc_isoformat(),
    }


def fetch_weather_tool(location: dict[str, Any], user_message: str = "") -> dict[str, Any]:
    """Return weather data and error details for a resolved location."""
    target_date = _target_date_from_message(user_message)
    try:
        return {"weather": _fetch_open_meteo_weather(location, target_date), "api_errors": []}
    except Exception as exc:
        logger.warning("[environment_tool.fetch_weather] Open-Meteo failed, using fallback: %s", exc)
        return {
            "weather": _mock_weather(location, target_date),
            "api_errors": [f"Open-Meteo weather query failed: {exc}"],
        }

tool_registry.register(
    "resolve_location",
    "Resolve a user location query to city, latitude, longitude, and timezone.",
    resolve_location_tool,
    {
        "type": "object",
        "properties": {"query": {"type": "string"}},
        "required": ["query"],
    },
)
tool_registry.register(
    "fetch_air_quality",
    "Fetch air quality data for a resolved location.",
    fetch_air_quality_tool,
    {
        "type": "object",
        "properties": {"location": {"type": "object"}},
        "required": ["location"],
    },
)
tool_registry.register(
    "fetch_weather",
    "Fetch weather data for a resolved location and user date expression.",
    fetch_weather_tool,
    {
        "type": "object",
        "properties": {
            "location": {"type": "object"},
            "user_message": {"type": "string"},
        },
        "required": ["location"],
    },
)
