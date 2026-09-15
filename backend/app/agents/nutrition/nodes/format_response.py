"""Format Response Node for Nutrition Agent."""

import logging
from typing import Any, Dict, List

from ..state import NutritionState

logger = logging.getLogger(__name__)


async def format_response(state: dict) -> dict:
    """Format the final response for the user.

    This node formats all the analysis results into a clear,
    user-friendly response with Markdown formatting.

    Args:
        state: Current state dict with all analysis results

    Returns:
        Updated state dict with formatted response
    """
    logger.info("[format_response] Formatting response")

    try:
        foods = state.get('extracted_foods', [])
        total = state.get('total_nutrition', {})

        if not foods:
            state['response'] = """## 🍎 营养分析报告

这次我还没有成功识别出您具体吃了哪些食物，所以暂时没法给出准确的营养计算结果。

您可以这样补充描述，我就能继续帮您分析：
- 具体食物名称
- 大概份量
- 烹饪方式

例如：`早餐吃了2个水煮蛋、250ml牛奶、2片全麦面包`

---
*💊 本分析仅供参考，不能替代专业医疗建议。如有特殊健康状况，请咨询专业医生或营养师。*"""
            logger.info("[format_response] Returned fallback response because no foods were extracted")
            return state

        # Build response sections
        sections = []

        # Title
        sections.append("## 🍎 营养分析报告\n")

        # Food summary
        if foods:
            sections.append("**分析的食物：**")
            for food in foods:
                name = food.get("name", "")
                amount = food.get("amount", "")
                unit = food.get("unit", "")
                category = food.get("category", "")
                sections.append(f"- {name} ({amount}{unit}) [{category}]")
            sections.append("")

        # Nutrition summary
        if total:
            sections.append("**营养总览（每100g）：**")
            sections.append(f"- 🔥 热量：{total.get('calories', 0):.0f} kcal")
            sections.append(f"- 🥩 蛋白质：{total.get('protein', 0):.1f}g")
            sections.append(f"- 🍚 碳水化合物：{total.get('carbs', 0):.1f}g")
            sections.append(f"- 🥑 脂肪：{total.get('fat', 0):.1f}g")
            sections.append(f"- 🌾 膳食纤维：{total.get('fiber', 0):.1f}g")
            sections.append("")

        # Health score
        score = state.get('health_score', 0)
        if score > 0:
            emoji = "🌟" if score >= 80 else "✨" if score >= 60 else "💪" if score >= 40 else "📝"
            sections.append(f"**健康评分：{emoji} {score:.0f}/100**")
            sections.append("")

        # Nutrition analysis
        analysis = state.get('nutrition_analysis', '')
        if analysis:
            sections.append("**营养分析：**")
            sections.append(analysis)
            sections.append("")

        # Recommendations
        recommendations = state.get('recommendations', [])
        if recommendations:
            sections.append("**💡 饮食建议：**")
            for i, rec in enumerate(recommendations, 1):
                sections.append(f"{i}. {rec}")
            sections.append("")

        # Alternative foods
        alternatives = state.get('alternative_foods', [])
        if alternatives:
            sections.append("**🔄 健康替代建议：**")
            seen = set()
            for alt in alternatives:
                orig = alt.get("original_food", "")
                if orig not in seen:
                    seen.add(orig)
                    alt_name = alt.get("alternative", "")
                    benefit = alt.get("benefit", "")
                    sections.append(f"- 用 **{alt_name}** 替代 {orig}：{benefit}")
            sections.append("")

        # Disclaimer
        sections.append("---")
        sections.append("*💊 本分析仅供参考，不能替代专业医疗建议。如有特殊健康状况，请咨询专业医生或营养师。*")

        # Combine all sections
        response = "\n".join(sections)

        # Update state
        state['response'] = response

        logger.info("[format_response] Response formatted successfully")

        return state

    except Exception as e:
        logger.error(f"[format_response] Error: {e}")
        # Create a simple fallback response
        extracted_foods = state.get('extracted_foods', [])
        total_nutrition = state.get('total_nutrition', {})
        health_score = state.get('health_score', 0)
        state['response'] = f"""## 🍎 营养分析报告

**分析的食物：**
{chr(10).join([f"- {f.get('name', '')}" for f in extracted_foods])}

**营养总览：**
- 🔥 热量：{total_nutrition.get('calories', 0):.0f} kcal
- 🥩 蛋白质：{total_nutrition.get('protein', 0):.1f}g
- 🍚 碳水化合物：{total_nutrition.get('carbs', 0):.1f}g
- 🥑 脂肪：{total_nutrition.get('fat', 0):.1f}g

**健康评分：{health_score:.0f}/100**

*注意：响应格式化过程中出现错误，以上为简化版报告。*
"""
        return state
