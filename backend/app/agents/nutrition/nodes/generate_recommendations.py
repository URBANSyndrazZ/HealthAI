"""Generate Recommendations Node for Nutrition Agent."""

import logging
from typing import Any, Dict, List

from app.llm.deepseek import DeepSeekClient

from ..state import NutritionState

logger = logging.getLogger(__name__)


async def generate_recommendations(state: dict) -> dict:
    """Generate personalized nutrition recommendations.

    This node generates:
    - Dietary recommendations based on nutrition analysis
    - Alternative food suggestions
    - Tips for healthier eating

    Args:
        state: Current NutritionState

    Returns:
        Updated NutritionState with recommendations
    """
    logger.info(f"[generate_recommendations] Generating recommendations for user {state.get('user_id', 'unknown')}")

    try:
        # Get nutrition data
        total = state.get('total_nutrition', {})
        analysis = state.get('nutrition_analysis', '')
        health_score = state.get('health_score', 0)
        foods = state.get("extracted_foods", [])

        if not foods:
            state['recommendations'] = [
                "这次没有成功识别出具体食物，建议把每样食物名称、份量和做法说得更具体一些。",
                "例如可以描述为“午餐吃了一碗米饭、150g鸡胸肉和一份西兰花”，这样更容易得到准确分析。",
            ]
            state['alternative_foods'] = []
            return state

        # Get user health goals and restrictions
        goals = state.get('user_health_goals', [])
        restrictions = state.get('dietary_restrictions', [])

        # Initialize LLM
        llm = DeepSeekClient()

        # Build system prompt and user message for recommendations
        system_prompt = "You are a professional nutritionist. Provide personalized dietary recommendations based on meal analysis."
        user_message = f"""Provide personalized dietary recommendations based on this meal analysis:

**Nutritional Summary:**
- Total Calories: {total.get('calories', 0):.0f} kcal
- Protein: {total.get('protein', 0):.1f}g
- Carbohydrates: {total.get('carbs', 0):.1f}g
- Fat: {total.get('fat', 0):.1f}g
- Fiber: {total.get('fiber', 0):.1f}g

**Nutritional Analysis:**
{analysis}

**Health Score:** {health_score:.0f}/100

**User Context:**
- Health Goals: {', '.join(goals) if goals else 'Not specified'}
- Dietary Restrictions: {', '.join(restrictions) if restrictions else 'None'}

**Task:**
Provide 3-5 specific, actionable recommendations in Chinese (each 1-2 sentences):

1. Immediate improvements for this meal
2. Balancing macronutrients if needed
3. Foods to add or reduce
4. Timing or portion suggestions
5. Alignment with user goals/restrictions

Make recommendations specific, practical, and encouraging. Avoid being preachy or negative.

Return the recommendations as a numbered list in Chinese."""

        # Call LLM
        try:
            response = await llm.chat(system_prompt=system_prompt, user_message=user_message)
            content = response.strip()
        except Exception as e:
            logger.error(f"[generate_recommendations] LLM error: {e}")
            content = ""

        if content:
            # Parse recommendations from response
            recommendations = []
            for line in content.split('\n'):
                line = line.strip()
                # Look for numbered items
                if line and (line[0].isdigit() or line.startswith('-') or line.startswith('•')):
                    # Remove numbering/bullets
                    rec = line
                    if '.' in line[:5]:
                        rec = line.split('.', 1)[1].strip()
                    elif line.startswith('-') or line.startswith('•'):
                        rec = line[1:].strip()
                    if rec:
                        recommendations.append(rec)

            # If no recommendations parsed, use fallback
            if not recommendations:
                recommendations = _generate_fallback_recommendations(state)

            state['recommendations'] = recommendations
        else:
            # Use fallback recommendations when LLM fails
            state['recommendations'] = _generate_fallback_recommendations(state)

        # Generate alternative food suggestions
        state['alternative_foods'] = _generate_alternatives(state)

        logger.info(f"[generate_recommendations] Generated {len(state['recommendations'])} recommendations")

        return state

    except Exception as e:
        logger.error(f"[generate_recommendations] Error: {e}")
        state['error'] = f"Failed to generate recommendations: {e}"
        state['recommendations'] = _generate_fallback_recommendations(state)
        return state


def _generate_fallback_recommendations(state: dict) -> List[str]:
    """Generate fallback recommendations when LLM fails."""
    recommendations = []
    total = state.get('total_nutrition', {})

    # Check protein
    if total.get("protein", 0) < 15:
        recommendations.append("考虑添加优质蛋白质来源，如鸡胸肉、鱼类或豆制品，有助于维持肌肉健康。")

    # Check fiber
    if total.get("fiber", 0) < 5:
        recommendations.append("建议增加蔬菜或全谷物的摄入，提高膳食纤维含量，有助于消化健康。")

    # Check fat
    if total.get("fat", 0) > 25:
        recommendations.append("这餐的脂肪含量较高，建议下一餐选择更清淡的烹饪方式。")

    # General advice
    recommendations.append("保持饮食多样化，确保摄入各类营养素，维持均衡饮食。")

    return recommendations


def _generate_alternatives(state: dict) -> List[Dict[str, Any]]:
    """Generate alternative food suggestions."""
    alternatives = []

    # Map of foods to healthier alternatives
    alternative_map = {
        "白米饭": [
            {"name": "糙米饭", "benefit": "富含膳食纤维，血糖上升更慢"},
            {"name": "燕麦", "benefit": "含有β-葡聚糖，有助于降低胆固醇"},
        ],
        "白面包": [
            {"name": "全麦面包", "benefit": "更高的纤维含量，饱腹感更强"},
        ],
        "炸鸡": [
            {"name": "烤鸡胸肉", "benefit": "减少脂肪摄入，保留优质蛋白"},
            {"name": "蒸鱼", "benefit": "富含Omega-3脂肪酸，有益心脏健康"},
        ],
        "猪肉": [
            {"name": "鸡胸肉", "benefit": "更低的脂肪含量，高蛋白"},
            {"name": "鱼类", "benefit": "优质蛋白，含有益心脏的脂肪酸"},
        ],
        "含糖饮料": [
            {"name": "无糖茶", "benefit": "零热量，含有抗氧化物质"},
            {"name": "柠檬水", "benefit": "清爽解渴，促进维生素C摄入"},
        ],
    }

    # Check for foods that have alternatives
    for food in state.get('extracted_foods', []):
        food_name = food.get("name", "")
        for key, alts in alternative_map.items():
            if key in food_name or food_name in key:
                for alt in alts:
                    alternatives.append({
                        "original_food": food_name,
                        "alternative": alt["name"],
                        "benefit": alt["benefit"],
                    })

    return alternatives[:5]  # Return top 5 alternatives
