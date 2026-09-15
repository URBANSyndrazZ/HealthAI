import hashlib
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.agents.environment import EnvironmentAgent, EnvironmentState
from app.agents.exercise import ExerciseAgent, ExerciseState
from app.agents.nutrition import NutritionAgent, NutritionState
from app.api.deps import get_current_user
from app.core import cache_manager
from app.core.observability import get_trace_id
from app.core.prompt_security import assess_prompt_injection

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agents", tags=["agents"])

def _resolve_user_id(request_user_id: str|None, current_user: Any) -> str:
    return str(getattr(current_user, "id", "anonymous"))

def _stable_cache_key(prefix: str, user_id: str, payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:16]
    return f"{prefix}:{user_id}:{digest}"

async def _safe_cache_get(cache_key: str) -> Any|None:
    try:
        return await cache_manager.get(cache_key)
    except Exception as exc:
        logger.warning("Cache read failed for %s: %s", cache_key, exc)
        return None

async def _safe_cache_set(cache_key: str, value: Any, ttl: int = 300):
    try:
        await cache_manager.set(cache_key, value, ttl)
    except Exception as exc:
        logger.warning("Cache write failed for %s: %s", cache_key, exc)

def _without_runtime_fields(payload: Any) -> dict[str, Any]:
    data = dict(payload or {})
    data.pop("trace_id", None)
    data.pop("prompt_security", None)
    return data

# ==================== Request/Response Models ====================
class NutritionAnalyzeRequest(BaseModel):
    """Request model for nutrition analysis."""
    description: str = Field(..., description="Food description or meal description")
    user_id: str | None = Field(None, description="User ID for personalized recommendations")

class NutritionAnalyzeResponse(BaseModel):
    """Response model for nutrition analysis."""
    success: bool
    trace_id: str = ""
    prompt_security: dict = {}
    foods: list[dict] = []
    total_nutrition: dict = {}
    health_score: float = 0.0
    recommendations: list[str] = []
    response: str = ""

class EnvironmentQueryRequest(BaseModel):
    """Request model for environment query."""
    location: str = Field(..., description="City name or location query (e.g., '北京市')")
    query_type: str = Field("all", description="Query type: 'air', 'weather', 'all'")

class EnvironmentQueryResponse(BaseModel):
    """Response model for environment query."""
    success: bool
    trace_id: str = ""
    prompt_security: dict = {}
    location: dict = {}
    air_quality: dict | None = None
    weather: dict | None = None
    health_risk: dict | None = None
    recommendations: list[dict] = []
    response: str = ""

class ExercisePlanRequest(BaseModel):
    """Request model for exercise plan."""
    goal: str = Field(..., description="Fitness goal (e.g., '减脂', '增肌', '健康')")
    fitness_level: str = Field("beginner", description="Fitness level: 'beginner', 'intermediate', 'advanced'")
    time_minutes: int = Field(30, description="Available time in minutes")
    user_id: str | None = Field(None, description="User ID for personalized plan")

class ExercisePlanResponse(BaseModel):
    """Response model for exercise plan."""
    success: bool
    trace_id: str = ""
    prompt_security: dict = {}
    workout_plan: dict = {}
    exercises: list[dict] = []
    safety_notes: list[str] = []
    fitness_level: str = ""
    fitness_goals: list[str] = []
    response: str = ""

# ==================== Nutrition Agent Endpoints ====================
@router.post("/nutrition/analyze", response_model=NutritionAnalyzeResponse)
async def analyze_nutrition(
    api_request: Request,
    request: NutritionAnalyzeRequest,
    current_user: Any = Depends(get_current_user)
) -> NutritionAnalyzeResponse:
    """Analyze food nutrition and provide dietary recommendations.

    Args:
        request: Nutrition analysis request with food description
        current_user: Current authenticated user

    Returns:
        Nutrition analysis results including food breakdown,
        nutrition data, health score, and recommendations
    """
    try:
        user_id = _resolve_user_id(request.user_id, current_user)
        trace_id = getattr(api_request.state, "trace_id", get_trace_id())
        prompt_security = assess_prompt_injection(request.description).model_dump()
        logger.info(
            "[nutrition/analyze] trace=%s analyzing=%s user=%s prompt_security=%s",
            trace_id,
            request.description[:50],
            user_id,
            prompt_security.get("risk_level"),
        )

        # Check cache first
        cache_key = _stable_cache_key("nutrition", user_id, {"description": request.description})
        cache_result = await _safe_cache_get(cache_key)
        if cache_result:
            logger.info(f"[nutrition/analyze] Cache hit for {request.description[:30]}...")
            return NutritionAnalyzeResponse(
                **_without_runtime_fields(cache_result),
                trace_id=trace_id,
                prompt_security=prompt_security
            )

        # Create agent
        agent = NutritionAgent()

        # Create state
        state = NutritionState(
            user_message=request.description,
            user_id=user_id
        )

        # Porcess
        result = await agent.process(state)

        response = NutritionAnalyzeResponse(
            success=True,
            trace_id=trace_id,
            # prompt_security=prompt_security,
            foods=result.get('extracted_foods', []),
            total_nutrition=result.get('total_nutrition', {}),
            health_score=result.get('health_score', 0.0),
            recommendations=result.get('recommendations', []),
            response=result.get('response', "")
        )

        # Cache thr result
        await _safe_cache_set(cache_key, _without_runtime_fields(response.model_dump()), 300)
        logger.info(f"[nutrition/analyze] Cached result for {request.description[:30]}...")

        return response

    except Exception as e:
        logger.error(f"[nutrition/analyze] Error: {e}")
        return NutritionAnalyzeResponse(
            success=False,
            trace_id=get_trace_id(),
            response=f"分析失败: {str(e)}"
        )

# ==================== Environment Agent Endpoints ====================

@router.post("/environment/query", response_model=EnvironmentQueryResponse)
async def query_environment(
    api_request: Request,
    request: EnvironmentQueryRequest,
    current_user: Any = Depends(get_current_user),
) -> EnvironmentQueryResponse:
    """Query environment data (air quality, weather) for a location.

    Args:
        request: Environment query request with location
        current_user: Current authenticated user

    Returns:
        Environment data including air quality, weather,
        health risk assessment, and recommendations
    """
    try:
        user_id = _resolve_user_id(None, current_user)
        trace_id = getattr(api_request.state, "trace_id", get_trace_id())
        prompt_security = assess_prompt_injection(request.location).model_dump()
        cache_key = _stable_cache_key(
            "environment",
            user_id,
            {"location": request.location, "query_type": request.query_type},
        )

        # Check cache first
        cached_result = await _safe_cache_get(cache_key)
        if cached_result:
            logger.info(f"[environment/query] Cache hit for {request.location}")
            return EnvironmentQueryResponse(
                **_without_runtime_fields(cached_result),
                trace_id=trace_id,
                prompt_security=prompt_security,
            )

        logger.info(
            "[environment/query] trace=%s querying=%s prompt_security=%s",
            trace_id,
            request.location,
            prompt_security.get("risk_level"),
        )

        # Create agent
        agent = EnvironmentAgent()

        # Create state
        state = EnvironmentState(
            user_message=f"查询{request.location}的环境信息",
            user_id=user_id,
        )
        state.location_query = request.location

        # Process
        result = await agent.process(state)

        # Filter results based on query_type
        air_quality = result.get('air_quality')
        weather = result.get('weather')

        if request.query_type == 'air':
            weather = None
        elif request.query_type == 'weather':
            air_quality = None

        response = EnvironmentQueryResponse(
            success=True,
            trace_id=trace_id,
            prompt_security=prompt_security,
            location=result.get('location', {}),
            air_quality=air_quality,
            weather=weather,
            health_risk=result.get('health_risk'),
            recommendations=result.get('recommendations', []),
            response=result.get('response', ''),
        )

        # Cache the result
        await _safe_cache_set(cache_key, _without_runtime_fields(response.model_dump()), 300)
        logger.info(f"[environment/query] Cached result for {request.location}")

        return response

    except Exception as e:
        logger.error(f"[environment/query] Error: {e}")
        return EnvironmentQueryResponse(
            success=False,
            trace_id=get_trace_id(),
            response=f"查询失败: {str(e)}",
        )


# ==================== Exercise Agent Endpoints ====================

@router.post("/exercise/plan", response_model=ExercisePlanResponse)
async def create_exercise_plan(
    api_request: Request,
    request: ExercisePlanRequest,
    current_user: Any = Depends(get_current_user),
) -> ExercisePlanResponse:
    """Create a personalized exercise plan.

    Args:
        request: Exercise plan request with fitness goal and preferences
        current_user: Current authenticated user

    Returns:
        Personalized workout plan including exercises,
        safety notes, and recommendations
    """
    try:
        user_id = _resolve_user_id(request.user_id, current_user)
        trace_id = getattr(api_request.state, "trace_id", get_trace_id())
        prompt_security = assess_prompt_injection(
            f"{request.goal} {request.fitness_level} {request.time_minutes}"
        ).model_dump()
        cache_key = _stable_cache_key(
            "exercise",
            user_id,
            {
                "goal": request.goal,
                "fitness_level": request.fitness_level,
                "time_minutes": request.time_minutes,
            },
        )

        # Check cache first
        cached_result = await _safe_cache_get(cache_key)
        if cached_result:
            logger.info(f"[exercise/plan] Cache hit for {request.goal}")
            return ExercisePlanResponse(
                **_without_runtime_fields(cached_result),
                trace_id=trace_id,
                prompt_security=prompt_security,
            )

        logger.info(
            "[exercise/plan] trace=%s creating plan=%s level=%s prompt_security=%s",
            trace_id,
            request.goal,
            request.fitness_level,
            prompt_security.get("risk_level"),
        )

        # Create agent
        agent = ExerciseAgent()

        # Create state
        state = ExerciseState(
            user_message=f"我想要{request.goal}，适合{request.fitness_level}，{request.time_minutes}分钟",
            user_id=user_id,
        )

        # Set additional state properties
        state.fitness_level = request.fitness_level
        state.fitness_goals = [request.goal]
        state.time_available = request.time_minutes

        # Process
        result = await agent.process(state)

        # Build response
        response = ExercisePlanResponse(
            success=True,
            trace_id=trace_id,
            prompt_security=prompt_security,
            workout_plan=result.get('workout_plan', {}),
            exercises=result.get('exercises', []),
            safety_notes=result.get('safety_notes', []),
            fitness_level=result.get('fitness_level', ''),
            fitness_goals=result.get('fitness_goals', []),
            response=result.get('response', ''),
        )

        # Cache the result
        await _safe_cache_set(cache_key, _without_runtime_fields(response.model_dump()), 300)
        logger.info(f"[exercise/plan] Cached result for {request.goal}")

        return response

    except Exception as e:
        logger.error(f"[exercise/plan] Error: {e}")
        return ExercisePlanResponse(
            success=False,
            trace_id=get_trace_id(),
            response=f"创建计划失败: {str(e)}",
        )