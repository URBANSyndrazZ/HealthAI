"""Optionally refine the rule-based exercise plan with an LLM."""

from __future__ import annotations

import copy
import logging
from typing import Any

from app.config import settings
from app.llm.deepseek import deepseek_client
from app.rag.retriever import rag_retriever

logger = logging.getLogger(__name__)


def _profile_memory_summary(profile: dict[str, Any], state: dict[str, Any]) -> str:
    memory_parts: list[str] = []
    for key in ("exercise", "lifestyle", "health_goals"):
        value = profile.get(key) if isinstance(profile, dict) else None
        if value:
            memory_parts.append(f"{key}: {value}")
    if state.get("memory_context"):
        memory_parts.append(str(state["memory_context"]))
    return "\n".join(memory_parts) or "暂无明确历史运动习惯。"


def _environment_context(state: dict[str, Any]) -> dict[str, Any]:
    if state.get("environment_data"):
        return state["environment_data"]

    prior_results = state.get("prior_results") or {}
    if not isinstance(prior_results, dict):
        return {}

    if isinstance(prior_results.get("environment"), dict):
        return prior_results["environment"]

    response = prior_results.get("environment_analysis")
    if isinstance(response, dict):
        return response.get("result") or response

    return {}


async def _retrieve_exercise_guidelines(state: dict[str, Any]) -> list[dict[str, Any]]:
    existing = state.get("rag_guidelines")
    if isinstance(existing, list) and existing:
        return existing[:3]

    goals = "、".join(state.get("fitness_goals") or [])
    query = f"运动计划 身体活动 指南 {goals} {state.get('fitness_level', '')}".strip()
    try:
        docs = await rag_retriever.retrieve(query)
        return [
            {
                "id": doc.get("id"),
                "title": doc.get("title", ""),
                "content": doc.get("content", "")[:600],
                "source": doc.get("source", ""),
                "metadata": doc.get("metadata", {}),
            }
            for doc in docs[:3]
        ]
    except Exception as exc:
        logger.warning("[llm_refine_plan] RAG guideline retrieval skipped: %s", exc)
        return []


def _safe_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


async def llm_refine_plan(state: dict[str, Any]) -> dict[str, Any]:
    """Use an LLM to refine the baseline plan, without making it mandatory."""
    if not state.get("baseline_workout_plan"):
        state["baseline_workout_plan"] = copy.deepcopy(state.get("workout_plan", {}))
        state["baseline_exercises"] = copy.deepcopy(state.get("exercises", []))
        state["baseline_safety_notes"] = copy.deepcopy(state.get("safety_notes", []))

    if not settings.exercise_llm_refine_enabled:
        state["llm_refine_status"] = "skipped_disabled"
        return state

    if not settings.deepseek_api_key:
        state["llm_refine_status"] = "skipped_no_api_key"
        return state

    guidelines = await _retrieve_exercise_guidelines(state)
    state["rag_guidelines"] = guidelines

    profile = state.get("user_profile") or {}
    environment = _environment_context(state)
    prompt = f"""请在不突破安全约束的前提下,优化这个baseline运动计划。

用户问题:
{state.get("user_message", "")}

用户目标与体能:
- fitness_level: {state.get("fitness_level", "beginner")}
- fitness_goals: {state.get("fitness_goals", [])}
- health_conditions: {state.get("health_conditions", [])}
- time_available: {state.get("time_available", 30)}分钟

历史运动习惯/用户画像:
{_profile_memory_summary(profile, state)}

环境结果:
{environment or "暂无环境结果"}

RAG运动指南片段:
{guidelines or "暂无RAG指南片段"}

硬性安全约束,不得删除或弱化:
{state.get("safety_notes", [])}

baseline计划:
workout_plan={state.get("workout_plan", {})}
exercises={state.get("exercises", [])}

请只返回JSON,字段:
{{
  "workout_plan": {{...}},
  "exercises": [
    {{"name": "动作", "duration": 20, "intensity": "低/中/高", "description": "说明", "type": "cardio/strength/flexibility"}}
  ],
  "additional_safety_notes": ["补充安全提示"],
  "rationale": "优化理由"
}}
"""
    try:
        result = await deepseek_client.json_chat(
            system_prompt=(
                "你是谨慎的运动规划师。只能在已有baseline基础上优化表达和安排,"
                "不得突破安全约束,不得编造不存在的医学结论。"
            ),
            user_message=prompt,
        )
    except Exception as exc:
        logger.warning("[llm_refine_plan] LLM refine failed: %s", exc)
        state["llm_refine_status"] = "failed"
        return state

    if not isinstance(result, dict) or "raw_response" in result:
        state["llm_refine_status"] = "invalid_response"
        return state

    refined_plan = result.get("workout_plan")
    refined_exercises = result.get("exercises")
    if isinstance(refined_plan, dict) and refined_plan:
        merged_plan = {**state.get("workout_plan", {}), **refined_plan}
        merged_plan["refined_by_llm"] = True
        state["workout_plan"] = merged_plan
    if isinstance(refined_exercises, list) and refined_exercises:
        state["exercises"] = [item for item in refined_exercises if isinstance(item, dict)]

    additional_notes = [
        str(note).strip()
        for note in _safe_list(result.get("additional_safety_notes"))
        if str(note).strip()
    ]
    state["safety_notes"] = list(dict.fromkeys([*state.get("safety_notes", []), *additional_notes]))
    state["llm_refine_rationale"] = str(result.get("rationale") or "")
    state["llm_refine_status"] = "success"
    logger.info("[llm_refine_plan] Refined exercise plan with LLM")
    return state
