"""Agent processing tasks.

This module provides background tasks for:
- Async agent processing
- Batch agent operations
- Agent result caching
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any

from app.core.celery import celery_app
from app.core.cache import cache_manager, AGENT_RESULT_TTL
from app.agents.nutrition import NutritionAgent, NutritionState
from app.agents.environment import EnvironmentAgent, EnvironmentState
from app.agents.exercise import ExerciseAgent, ExerciseState

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async agent/cache operation from a synchronous Celery worker."""
    return asyncio.run(coro)


def _state_to_dict(result: Any) -> Dict[str, Any]:
    if hasattr(result, "to_dict"):
        return result.to_dict()
    return dict(result)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def process_nutrition_async(
    self,
    user_message: str,
    user_id: str,
    cache_key: Optional[str] = None
) -> Dict[str, Any]:
    """Process nutrition analysis asynchronously.

    Args:
        user_message: Food description
        user_id: User ID
        cache_key: Optional cache key to store result

    Returns:
        Nutrition analysis result
    """
    try:
        logger.info(f"[process_nutrition_async] Processing for user {user_id}")

        agent = NutritionAgent()
        state = NutritionState(
            user_message=user_message,
            user_id=user_id
        )

        result = _state_to_dict(_run_async(agent.process(state)))

        # Cache result if key provided
        if cache_key:
            try:
                _run_async(cache_manager.set(cache_key, result, ttl=AGENT_RESULT_TTL))
                logger.info(f"[process_nutrition_async] Cached result for {cache_key}")
            except Exception as e:
                logger.warning(f"[process_nutrition_async] Failed to cache: {e}")

        return result

    except Exception as exc:
        logger.error(f"[process_nutrition_async] Failed: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def process_environment_async(
    self,
    location: str,
    user_id: str,
    query_type: str = "all",
    cache_key: Optional[str] = None
) -> Dict[str, Any]:
    """Process environment query asynchronously.

    Args:
        location: Location to query
        user_id: User ID
        query_type: Query type (air, weather, all)
        cache_key: Optional cache key

    Returns:
        Environment query result
    """
    try:
        logger.info(f"[process_environment_async] Querying {location} for user {user_id}")

        agent = EnvironmentAgent()
        state = EnvironmentState(
            user_message=f"查询{location}的环境信息",
            user_id=user_id,
        )
        state.location_query = location

        result = _state_to_dict(_run_async(agent.process(state)))

        # Filter results
        if query_type == "air":
            result.pop('weather', None)
        elif query_type == "weather":
            result.pop('air_quality', None)

        # Cache result
        if cache_key:
            try:
                _run_async(cache_manager.set(cache_key, result, ttl=AGENT_RESULT_TTL))
                logger.info(f"[process_environment_async] Cached result for {cache_key}")
            except Exception as e:
                logger.warning(f"[process_environment_async] Failed to cache: {e}")

        return result

    except Exception as exc:
        logger.error(f"[process_environment_async] Failed: {exc}")
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=30)
def process_exercise_async(
    self,
    goal: str,
    fitness_level: str,
    time_minutes: int,
    user_id: str,
    cache_key: Optional[str] = None
) -> Dict[str, Any]:
    """Process exercise plan asynchronously.

    Args:
        goal: Fitness goal
        fitness_level: Fitness level
        time_minutes: Available time
        user_id: User ID
        cache_key: Optional cache key

    Returns:
        Exercise plan result
    """
    try:
        logger.info(f"[process_exercise_async] Creating plan for user {user_id}")

        agent = ExerciseAgent()
        state = ExerciseState(
            user_message=f"我想要{goal}，适合{fitness_level}，{time_minutes}分钟",
            user_id=user_id
        )
        state.fitness_level = fitness_level
        state.fitness_goals = [goal]
        state.time_available = time_minutes

        result = _state_to_dict(_run_async(agent.process(state)))

        # Cache result
        if cache_key:
            try:
                _run_async(cache_manager.set(cache_key, result, ttl=AGENT_RESULT_TTL))
                logger.info(f"[process_exercise_async] Cached result for {cache_key}")
            except Exception as e:
                logger.warning(f"[process_exercise_async] Failed to cache: {e}")

        return result

    except Exception as exc:
        logger.error(f"[process_exercise_async] Failed: {exc}")
        raise self.retry(exc=exc)
