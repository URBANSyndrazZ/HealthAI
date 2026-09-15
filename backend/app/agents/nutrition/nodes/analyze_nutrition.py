"""Analyze Nutrition Node for Nutrition Agent."""

import logging
from typing import Any, Dict, List

from app.llm.deepseek import DeepSeekClient

from ..state import NutritionState

logger = logging.getLogger(__name__)


async def analyze_nutrition(state: dict) -> dict:
    """Analyze the nutritional composition of the food.

    This node analyzes the nutrition data to:
    - Calculate macro and micronutrient breakdown
    - Assess nutritional balance
    - Calculate health score
    - Identify strengths and concerns

    Args:
        state: Current state dict

    Returns:
        Updated state dict with nutrition analysis
    """
    nutrition_data = state.get('nutrition_data', {})
    logger.info(f"[analyze_nutrition] Analyzing nutrition for {len(nutrition_data.get('items', []))} items")

    try:
        # Get total nutrition
        total = state.get('total_nutrition', {})

        if not total or total.get("calories", 0) == 0:
            logger.warning("[analyze_nutrition] No nutrition data to analyze")
            state['nutrition_analysis'] = "无法获取营养数据进行分析。"
            state['health_score'] = 0
            state['nutrition_analysis_status'] = "empty"
            return state

        # Calculate percentages
        total_grams = total.get("protein", 0) + total.get("carbs", 0) + total.get("fat", 0)

        if total_grams > 0:
            protein_pct = (total.get("protein", 0) / total_grams) * 100
            carbs_pct = (total.get("carbs", 0) / total_grams) * 100
            fat_pct = (total.get("fat", 0) / total_grams) * 100
        else:
            protein_pct = carbs_pct = fat_pct = 0

        # Calculate calories from each macro
        protein_cals = total.get("protein", 0) * 4
        carbs_cals = total.get("carbs", 0) * 4
        fat_cals = total.get("fat", 0) * 9
        total_cals = total.get("calories", 0)

        if total_cals > 0:
            protein_cals_pct = (protein_cals / total_cals) * 100
            carbs_cals_pct = (carbs_cals / total_cals) * 100
            fat_cals_pct = (fat_cals / total_cals) * 100
        else:
            protein_cals_pct = carbs_cals_pct = fat_cals_pct = 0

        # Calculate health score (0-100)
        health_score = _calculate_health_score(
            protein_pct, carbs_pct, fat_pct,
            total.get("fiber", 0),
            total.get("calories", 0)
        )
        state['health_score'] = health_score

        # Use LLM for detailed analysis
        llm = DeepSeekClient()

        system_prompt = "You are a nutrition expert. Provide a professional nutritional analysis."
        user_message = f"""Analyze this meal's nutritional composition:

**Nutritional Summary:**
- Total Calories: {total_cals:.0f} kcal
- Protein: {total.get('protein', 0):.1f}g ({protein_pct:.1f}% of weight, {protein_cals_pct:.1f}% of calories)
- Carbohydrates: {total.get('carbs', 0):.1f}g ({carbs_pct:.1f}% of weight, {carbs_cals_pct:.1f}% of calories)
- Fat: {total.get('fat', 0):.1f}g ({fat_pct:.1f}% of weight, {fat_cals_pct:.1f}% of calories)
- Fiber: {total.get('fiber', 0):.1f}g

**Health Score:** {health_score:.0f}/100

Provide a concise nutritional analysis in Chinese (3-5 sentences) covering:
1. Overall nutritional balance
2. Macronutrient distribution assessment
3. Any nutritional strengths or concerns

Be objective, professional, and actionable."""

        response = await llm.chat(system_prompt=system_prompt, user_message=user_message)

        state['nutrition_analysis'] = response.strip()
        state['nutrition_analysis_status'] = "success"

        logger.info(f"[analyze_nutrition] Analysis complete. Health score: {health_score}")

        return state

    except Exception as e:
        logger.error(f"[analyze_nutrition] Error: {e}")
        state['nutrition_analysis'] = "营养分析过程中出现错误，但已获取基础营养数据。"
        state['health_score'] = 50
        state['nutrition_analysis_status'] = "fallback"
        return state


def _calculate_health_score(
    protein_pct: float,
    carbs_pct: float,
    fat_pct: float,
    fiber: float,
    calories: float
) -> float:
    """Calculate a health score based on nutritional composition.

    Score ranges from 0-100 based on:
    - Balanced macronutrients (protein 15-30%, carbs 45-65%, fat 20-35%)
    - Adequate fiber (at least 3g per 100 calories)
    - Reasonable calorie content

    Returns:
        Health score from 0-100
    """
    score = 50.0  # Start at neutral

    # Check protein balance (ideal: 15-30%)
    if 15 <= protein_pct <= 30:
        score += 15
    elif 10 <= protein_pct < 15 or 30 < protein_pct <= 35:
        score += 10
    elif 5 <= protein_pct < 10 or 35 < protein_pct <= 40:
        score += 5
    else:
        score -= 5

    # Check carb balance (ideal: 45-65%)
    if 45 <= carbs_pct <= 65:
        score += 15
    elif 35 <= carbs_pct < 45 or 65 < carbs_pct <= 70:
        score += 10
    elif 25 <= carbs_pct < 35:
        score += 5
    else:
        score -= 5

    # Check fat balance (ideal: 20-35%)
    if 20 <= fat_pct <= 35:
        score += 15
    elif 15 <= fat_pct < 20 or 35 < fat_pct <= 40:
        score += 10
    elif 10 <= fat_pct < 15:
        score += 5
    else:
        score -= 5

    # Check fiber (ideal: at least 3g per 100 calories)
    if calories > 0:
        fiber_per_100cal = (fiber / calories) * 100
        if fiber_per_100cal >= 3:
            score += 10
        elif fiber_per_100cal >= 2:
            score += 5
        elif fiber_per_100cal >= 1:
            score += 2
        else:
            score -= 5

    # Ensure score is within 0-100 range
    return max(0.0, min(100.0, score))


def _generate_basic_analysis(
    protein_pct: float,
    carbs_pct: float,
    fat_pct: float,
    health_score: float
) -> str:
    """Generate a basic nutritional analysis when LLM is unavailable."""
    analysis_parts = []

    # Overall assessment
    if health_score >= 70:
        analysis_parts.append("这是一顿营养均衡的餐食。")
    elif health_score >= 50:
        analysis_parts.append("这顿餐食的营养搭配尚可，但仍有改善空间。")
    else:
        analysis_parts.append("这顿餐食的营养结构需要调整。")

    # Macronutrient analysis
    analysis_parts.append(f"蛋白质占总重量的{protein_pct:.1f}%，")
    analysis_parts.append(f"碳水化合物占{carbs_pct:.1f}%，")
    analysis_parts.append(f"脂肪占{fat_pct:.1f}%。")

    # Score
    analysis_parts.append(f"综合健康评分：{health_score:.0f}/100。")

    return "".join(analysis_parts)