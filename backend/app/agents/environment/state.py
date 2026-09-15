"""Environment Agent State Definition."""

from typing import Any, Dict, List, Optional, TypedDict


class LocationInfo(TypedDict):
    """Location information."""
    city: str
    country: str
    lat: float
    lon: float
    timezone: str


class AirQualityData(TypedDict):
    """Air quality data structure."""
    aqi: int  # Air Quality Index
    pm25: float  # PM2.5 (μg/m³)
    pm10: float  # PM10 (μg/m³)
    o3: float  # Ozone (μg/m³)
    no2: float  # Nitrogen dioxide (μg/m³)
    so2: float  # Sulfur dioxide (μg/m³)
    co: float  # Carbon monoxide (mg/m³)
    level: str  # "good", "moderate", "unhealthy_sensitive", "unhealthy", "very_unhealthy", "hazardous"
    primary_pollutant: str
    timestamp: str


class WeatherData(TypedDict):
    """Weather data structure."""
    temperature: float  # Celsius
    feels_like: float
    humidity: int  # Percentage
    pressure: int  # hPa
    wind_speed: float  # m/s
    wind_direction: str
    visibility: int  # meters
    uv_index: int
    weather_code: int
    weather_description: str
    precipitation_probability: int
    forecast: List[Dict[str, Any]]  # 3-7 day forecast
    timestamp: str


class TrafficData(TypedDict):
    """Traffic data structure."""
    congestion_level: str  # "low", "moderate", "high", "severe"
    average_speed: float  # km/h
    incidents: List[Dict[str, Any]]  # Traffic incidents
    road_conditions: str
    timestamp: str


class HealthRiskAssessment(TypedDict):
    """Health risk assessment."""
    overall_risk: str  # "low", "moderate", "high", "very_high"
    air_quality_risk: str
    weather_risk: str
    heat_stress_risk: str
    cold_stress_risk: str
    uv_risk: str
    allergen_risk: str
    sensitive_groups: List[str]  # "children", "elderly", "pregnant", "respiratory", "cardiovascular"
    warnings: List[str]
    precautions: List[str]


class EnvironmentRecommendation(TypedDict):
    """Environment-related recommendation."""
    category: str  # "outdoor_activity", "indoor_air", "exercise", "travel", "health_protection"
    priority: str  # "high", "medium", "low"
    title: str
    description: str
    action_items: List[str]
    best_time: Optional[str]
    avoid_time: Optional[str]


class EnvironmentState(dict):
    """State for Environment Analysis Agent.

    This class manages the state for environmental health analysis,
    including air quality, weather data, and health risk assessments.
    """

    def __init__(
        self,
        user_message: str = "",
        user_id: str = "anonymous",
        session_id: str = "",
    ):
        """Initialize environment state.

        Args:
            user_message: Original user message
            user_id: User identifier
            session_id: Session identifier
        """
        super().__init__()
        self.user_message = user_message
        self.user_id = user_id
        self.session_id = session_id

        # Location
        self.location_query: str = ""  # User's location query (e.g., "北京市")
        self.location: Optional[LocationInfo] = None

        # Environmental data
        self.air_quality: Optional[AirQualityData] = None
        self.weather: Optional[WeatherData] = None
        self.traffic: Optional[TrafficData] = None

        # API errors
        self.api_errors: List[str] = []

        # Analysis
        self.health_risk: Optional[HealthRiskAssessment] = None
        self.environment_summary: str = ""

        # Recommendations
        self.recommendations: List[EnvironmentRecommendation] = []
        self.llm_advice: str = ""
        self.llm_advice_status: str = "not_run"

        # Response
        self.response: str = ""
        self.citations: List[Dict[str, str]] = []

        # Error handling
        self.error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary."""
        return {
            "user_message": self.user_message,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "location_query": self.location_query,
            "location": self.location,
            "air_quality": self.air_quality,
            "weather": self.weather,
            "traffic": self.traffic,
            "api_errors": self.api_errors,
            "health_risk": self.health_risk,
            "environment_summary": self.environment_summary,
            "recommendations": self.recommendations,
            "llm_advice": self.llm_advice,
            "llm_advice_status": self.llm_advice_status,
            "response": self.response,
            "citations": self.citations,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EnvironmentState":
        """Create state from dictionary."""
        state = cls(
            user_message=data.get("user_message", ""),
            user_id=data.get("user_id", "anonymous"),
            session_id=data.get("session_id", ""),
        )
        state.location_query = data.get("location_query", "")
        state.location = data.get("location")
        state.air_quality = data.get("air_quality")
        state.weather = data.get("weather")
        state.traffic = data.get("traffic")
        state.api_errors = data.get("api_errors", [])
        state.health_risk = data.get("health_risk")
        state.environment_summary = data.get("environment_summary", "")
        state.recommendations = data.get("recommendations", [])
        state.llm_advice = data.get("llm_advice", "")
        state.llm_advice_status = data.get("llm_advice_status", "not_run")
        state.response = data.get("response", "")
        state.citations = data.get("citations", [])
        state.error = data.get("error")
        return state
