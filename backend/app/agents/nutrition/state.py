"""Nutrition Agent State Definition."""

from typing import Any, Dict, List, Optional, TypedDict


class FoodItem(TypedDict):
    """Food item with nutrition information."""
    name: str
    amount: float
    unit: str
    calories: float
    protein: float
    carbs: float
    fat: float
    fiber: Optional[float]
    vitamins: Optional[Dict[str, float]]
    minerals: Optional[Dict[str, float]]

class NutritionState(dict):
    """State for Nutrition Analysis Agent.

    This class manages the state for food nutrition analysis,
    including user input, extracted food items, nutrition data,
    and generated recommendations.
    """
    def __init__(
        self,
        user_message: str = "",
        user_id: str = "anonymous",
        session_id: str = "",
    ):
        """Initialize nutrition state.

        Args:
            user_message: Original user message
            user_id: User identifier
            session_id: Session identifier
        """
        super().__init__()
        self.user_message = user_message
        self.user_id = user_id
        self.session_id = session_id

        # Input analysis
        self.input_type: str = ""  # "text", "image", "mixed"
        self.food_description: str = ""

        # Food extraction
        self.extracted_foods: List[Dict[str, Any]] = []
        self.food_confidence: float = 0.0

        # Nutrition data
        self.nutrition_data: Dict[str, Any] = {}
        self.total_nutrition: Dict[str, float] = {}

        # Analysis
        self.nutrition_analysis: str = ""
        self.health_score: float = 0.0

        # Recommendations
        self.recommendations: List[str] = []
        self.alternative_foods: List[Dict[str, Any]] = []

        # User profile integration
        self.user_health_goals: List[str] = []
        self.dietary_restrictions: List[str] = []

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
            "input_type": self.input_type,
            "food_description": self.food_description,
            "extracted_foods": self.extracted_foods,
            "nutrition_data": self.nutrition_data,
            "total_nutrition": self.total_nutrition,
            "nutrition_analysis": self.nutrition_analysis,
            "health_score": self.health_score,
            "recommendations": self.recommendations,
            "response": self.response,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "NutritionState":
        """Create state from dictionary."""
        state = cls(
            user_message=data.get("user_message", ""),
            user_id=data.get("user_id", "anonymous"),
            session_id=data.get("session_id", ""),
        )
        state.input_type = data.get("input_type", "")
        state.food_description = data.get("food_description", "")
        state.extracted_foods = data.get("extracted_foods", [])
        state.nutrition_data = data.get("nutrition_data", {})
        state.total_nutrition = data.get("total_nutrition", {})
        state.nutrition_analysis = data.get("nutrition_analysis", "")
        state.health_score = data.get("health_score", 0.0)
        state.recommendations = data.get("recommendations", [])
        state.response = data.get("response", "")
        state.error = data.get("error")
        return state