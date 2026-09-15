"""Exercise Agent State Definition."""

from typing import Any, Dict, List, Optional


class ExerciseState(dict):
    """State for Exercise Planning Agent."""

    def __init__(
        self,
        user_message: str = "",
        user_id: str = "anonymous",
        session_id: str = "",
    ):
        super().__init__()
        self.user_message = user_message
        self.user_id = user_id
        self.session_id = session_id

        # User profile
        self.user_profile: Dict[str, Any] = {}
        self.fitness_level: str = "beginner"  # beginner, intermediate, advanced
        self.health_conditions: List[str] = []
        self.fitness_goals: List[str] = []

        # Exercise context
        self.exercise_type: str = ""  # cardio, strength, flexibility, mixed
        self.available_equipment: List[str] = []
        self.time_available: int = 30  # minutes
        self.location: str = "home"  # home, gym, outdoor
        self.prior_results: Dict[str, Any] = {}
        self.rag_guidelines: List[Dict[str, Any]] = []

        # Generated plan
        self.workout_plan: Dict[str, Any] = {}
        self.exercises: List[Dict[str, Any]] = []
        self.safety_notes: List[str] = []
        self.baseline_workout_plan: Dict[str, Any] = {}
        self.baseline_exercises: List[Dict[str, Any]] = []
        self.baseline_safety_notes: List[str] = []
        self.llm_refine_status: str = "not_run"
        self.llm_refine_rationale: str = ""

        # Analysis
        self.assessment: Dict[str, Any] = {}

        # Response
        self.response: str = ""
        self.error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_message": self.user_message,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "user_profile": self.user_profile,
            "fitness_level": self.fitness_level,
            "health_conditions": self.health_conditions,
            "fitness_goals": self.fitness_goals,
            "exercise_type": self.exercise_type,
            "available_equipment": self.available_equipment,
            "time_available": self.time_available,
            "location": self.location,
            "prior_results": self.prior_results,
            "rag_guidelines": self.rag_guidelines,
            "workout_plan": self.workout_plan,
            "exercises": self.exercises,
            "safety_notes": self.safety_notes,
            "baseline_workout_plan": self.baseline_workout_plan,
            "baseline_exercises": self.baseline_exercises,
            "baseline_safety_notes": self.baseline_safety_notes,
            "llm_refine_status": self.llm_refine_status,
            "llm_refine_rationale": self.llm_refine_rationale,
            "response": self.response,
        }
