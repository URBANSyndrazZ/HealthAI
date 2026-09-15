import logging
from typing import Any, Dict, List

from app.llm.deepseek import DeepSeekClient

logger = logging.getLogger(__name__)

async def extract_food(state: dict) -> dict:
    """Extract specific food items from the food description.

    This node analyzes the food description to:
    - Identify specific food items mentioned
    - Estimate quantities/amounts
    - Categorize foods (main dish, side, drink, etc.)

    Args:
        state: Current state dict

    Returns:
        Dict with only the changed keys (LangGraph requirement)
    """
    logger.info(f"[extract_food] Extracting foods from: {state.get('food_description', '')[:100]}...")

    try:
        # Initialize LLM client
        llm = DeepSeekClient()

        # Build system prompt and user message for food extraction
        system_prompt = "You are a food extraction specialist. Extract all food items from the user's description with their estimated quantities in JSON format."
        user_message = f"""Extract all food items from the following description:

        Food Description: {state.get('food_description', '')}
    
        Provide the following in JSON format:
        1. foods: An array of food items, each with:
           - name: The food item name (be specific, e.g., "grilled chicken breast" not just "meat")
           - amount: Estimated quantity as a number
           - unit: Unit of measurement (g, oz, cup, piece, slice, bowl, etc.)
           - category: Food category (protein, vegetable, fruit, grain, dairy, fat, beverage, condiment, other)
           - confidence: Your confidence in this extraction (0.0-1.0)
    
        2. meal_type: Type of meal described (breakfast, lunch, dinner, snack, beverage_only, mixed)
    
        3. total_items: Total number of distinct food items identified
    
        Be thorough and extract ALL food items mentioned. If quantities are not specified, use typical serving sizes as estimates.
    
        Return ONLY valid JSON without any markdown formatting or additional text."""

        # Call LLM
        response = await llm.json_chat(
            system_prompt=system_prompt,
            user_message=user_message,
        )

        # Parse response - response is already a dict from json_chat
        if "raw_response" in response:
            logger.error(f"[extract_food] LLM parsing error: {response}")
            # Fallback to simple extraction
            food_desc = state.get('food_description', '')
            return {
                "extracted_foods": [
                    {
                        "name": food_desc[:50] if food_desc else "unknown food",
                        "amount": 1,
                        "unit": "serving",
                        "category": "other",
                        "confidence": 0.5,
                    }
                ],
                "food_confidence": 0.5,
            }

        parsed = response

        # Get foods from parsed response
        foods = parsed.get("foods", [])
        if not isinstance(foods, list):
            foods = []
        food_confidence = sum(f.get("confidence", 0.5) for f in foods) / len(foods) if foods else 0.0

        # Log results
        logger.info(f"[extract_food] Extracted {len(foods)} food items")
        for food in foods:
            logger.info(f"  - {food.get('name')}: {food.get('amount')} {food.get('unit')} "
                        f"({food.get('category')}, conf={food.get('confidence')})")

        # Return only the changed keys (LangGraph requirement)
        result = {
            "extracted_foods": foods,
            "food_confidence": food_confidence,
            "food_extraction_status": "success" if foods else "empty",
        }
        logger.info(f"[extract_food] Returning keys: {list(result.keys())}")
        logger.info(f"[extract_food] Returning {len(foods)} foods")
        return result

    except Exception as e:
        logger.error(f"[extract_food] Error: {e}")
        # Fallback
        food_desc = state.get('food_description', '')
        return {
            "extracted_foods": [
                {
                    "name": food_desc[:50] if food_desc else "unknown food",
                    "amount": 1,
                    "unit": "serving",
                    "category": "other",
                    "confidence": 0.3,
                }
            ],
            "food_confidence": 0.3,
            "food_extraction_status": "fallback",
        }
