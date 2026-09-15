import logging
from typing import Any, Dict

from app.llm.deepseek import DeepSeekClient

logger = logging.getLogger(__name__)

async def parse_input(state: dict) -> dict:
    """Parse user input to understand the nutrition query."""
    logger.info(f"[parse_input] Parsing input: {state.get('user_message', '')[:100]}...")

    try:
        # Initialize LLM client
        llm = DeepSeekClient()

        # Build system prompt and user message for input parsing
        system_prompt = "You are a nutrition analysis assistant. Parse the user's input and extract structured information in JSON format."
        user_message = f"""Parse the following user input:
        User Input: {state.get('user_message', '')}

        Provide the following in JSON format:
        1. input_type: The type of input - "food_description" (describes food), "specific_food" (names specific food), "meal" (describes a meal), "dietary_question" (general nutrition question), or "mixed"
        2. food_description: Extract the food/meal description from the input
        3. query_intent: The user's intent - "nutrition_info" (wants nutrition facts), "dietary_advice" (wants recommendations), "meal_analysis" (wants analysis of a meal), "comparison" (comparing foods), or "general"
        4. specific_foods: List any specific food items mentioned

        Return ONLY valid JSON without any markdown formatting or additional text."""

        # Call LLM
        response = await llm.json_chat(system_prompt, user_message)

        # Parse response - response is already a dict from json_chat
        if "raw_response" in response:
            logger.error(f"[parse_input] LLM parsing error: {response}")
            # Fallback to simple parsing
            return {
                "input_type": "text",
                "food_description": state.get('user_message', ''),
            }

        parsed = response

        # Return only the changed keys
        result = {
            "input_type": parsed.get("input_type", "text"),
            "food_description": parsed.get("food_description", state.get('user_message', '')),
        }

        # Log results
        logger.info(f"[parse_input] Parsed input_type: {result['input_type']}")
        logger.info(f"[parse_input] Extracted food_description: {result['food_description'][:100]}...")

        return result

    except Exception as e:
        logger.error(f"[parse_input] Error: {e}")
        # Fallback
        return {
            "input_type": "text",
            "food_description": state.get('user_message', ''),
        }