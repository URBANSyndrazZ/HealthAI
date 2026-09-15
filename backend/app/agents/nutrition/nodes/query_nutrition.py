import logging
from typing import Any

import app.tools.nutrition  # noqa: F401 - registers nutrition tools
from app.tools.nutrition import NUTRITION_DB
from app.tools.executor import ToolExecutionContext, append_tool_trace, tool_executor

logger = logging.getLogger(__name__)

async def query_nutrition(state: dict) -> dict:
    """Query nutrition facts for extracted foods through registered tools."""
    extracted_foods = state.get("extracted_foods", [])
    logger.info("[query_nutrition] Querying nutrition data via tool for %d foods", len(extracted_foods))

    if not extracted_foods:
        logger.warning("[query_nutrition] No foods to query")
        return {
            "nutrition_data": {"items": [], "count": 0},
            "total_nutrition": {"calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0},
        }

    try:
        nutrition_results: list[dict[str, Any]] = []
        total_nutrition = {"calories": 0.0, "protein": 0.0, "carbs": 0.0, "fat": 0.0, "fiber": 0.0}

        for food in extracted_foods:
            food_name = food.get("food", "")
            amount = food.get("amount", 1.0)
            unit = food.get("unit", "serving")
            tool_result = await tool_executor.execute(
                "query_nutrition",
                context=ToolExecutionContext(
                    agent_name="nutrition",
                    trace_id=str(state.get("trace_id", "")),
                    user_id=str(state.get("user_id", "")),
                    session_id=str(state.get("session_id", "")),
                    required=False
                ),
                food_name=food_name,
                amount=amount,
                unit=unit
            )
            append_tool_trace(state, tool_result)
            if tool_result.status != "success":
                logger.warning("[query_nutrition] Tool failed for %s: %s", food_name, tool_result.error)
                continue

            nutrition_info = tool_result.data or {}

            nutrition_results.append(
                {
                    "food_name": food_name,
                    "amount": amount,
                    "unit": unit,
                    "nutrition_per_100g": nutrition_info.get("per_100g", {}),
                    "nutrition_total": nutrition_info.get("total", {}),
                    "data_source": nutrition_info.get("data_source", "nutrition_tool"),
                }
            )

            total = nutrition_info.get("total", {})
            for key in total_nutrition:
                total_nutrition[key] += total.get(key, 0)

        return {
            "nutrition_data": {"items": nutrition_results, "count": len(nutrition_results)},
            "total_nutrition": total_nutrition
        }

    except Exception as exc:
        logger.error("[query_nutrition] Tool query failed: %s", exc)
        return {
            "error": f"Failed to query nutrition data: {exc}",
            "nutrition_data": {"items": [], "count": 0},
            "total_nutrition": {"calories": 0, "protein": 0, "carbs": 0, "fat": 0, "fiber": 0},
        }