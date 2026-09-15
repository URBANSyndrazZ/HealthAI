"""Optional LLM personalization for environment advice."""

from __future__ import annotations

import logging

from app.config import settings
from app.llm.deepseek import deepseek_client

logger = logging.getLogger(__name__)


async def llm_generate_advice(state: dict) -> dict:
    """Generate a user-tailored explanation without changing factual fields."""
    if not settings.environment_llm_advice_enabled:
        state["llm_advice_status"] = "skipped_disabled"
        return state

    if not settings.deepseek_api_key:
        state["llm_advice_status"] = "skipped_no_api_key"
        return state

    prompt = f"""请基于以下结构化环境数据,生成一段更贴近用户问题的中文建议。

用户问题:
{state.get("user_message", "")}

位置:
{state.get("location", {})}

空气质量:
{state.get("air_quality", {})}

天气:
{state.get("weather", {})}

规则化风险评估:
{state.get("health_risk", {})}

规则生成的建议:
{state.get("recommendations", [])}

要求:
1. 只能解释和组织已有数据,不要编造天气、AQI、污染物或风险等级。
2. 不要降低已有风险提醒。
3. 如果数据缺失,明确说明局限性。
4. 控制在120字以内。
"""
    try:
        advice = await deepseek_client.chat(
            system_prompt=(
                "你是环境健康建议助手。事实字段来自工具和规则,你只负责把结构化结果"
                "改写成贴近用户问题的自然语言建议。"
            ),
            user_message=prompt,
        )
    except Exception as exc:
        logger.warning("[llm_generate_advice] LLM advice failed: %s", exc)
        state["llm_advice_status"] = "failed"
        return state

    advice = str(advice or "").strip()
    if not advice:
        state["llm_advice_status"] = "empty"
        return state

    state["llm_advice"] = advice[:500]
    state["llm_advice_status"] = "success"
    logger.info("[llm_generate_advice] Generated personalized environment advice")
    return state
