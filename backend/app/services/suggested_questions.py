"""Suggested question generation for chat entry points and follow-ups."""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.long_term import long_term_memory
from app.memory.profile import profile_manager
from app.models.chat import ChatMessage, ChatSession
from app.models.suggestion import SuggestedQuestionFeedback

logger = logging.getLogger(__name__)

GENERIC_QUESTIONS = {
    "您还有其他健康方面的问题吗",
    "您想了解更多关于这方面的信息吗",
    "还有其他问题吗",
    "还有什么可以帮您",
}

UNSAFE_TERMS = ("吃什么药", "用什么药", "药量", "剂量", "处方", "诊断我", "确诊")

DEFAULT_POOL = [
    "分析一下我最近的睡眠状态",
    "根据我的情况给一份运动建议",
    "帮我看看这周饮食是否均衡",
    "今天适合户外运动吗",
    "怎么安排更健康的作息",
    "我每天需要多少饮水量",
    "如何判断运动强度是否合适",
    "减脂期间饮食怎么搭配",
]


@dataclass(frozen=True)
class SuggestedQuestion:
    text: str
    score: float
    source: str


def _normalize_text(text: str) -> str:
    text = re.sub(r"\s+", "", str(text or ""))
    return text.strip("？?。！!，,；;：:、\"'“”‘’ ")


def _format_question(text: str) -> str:
    text = re.sub(r"\s+", "", str(text or "")).strip()
    text = text.strip("。！!，,；;：:、\"'“”‘’ ")
    if text and not text.endswith(("？", "?")):
        text = f"{text}？"
    return text


def filter_suggested_questions(
    questions: Iterable[str],
    *,
    current_question: str = "",
    limit: int = 3,
    fallback: Iterable[str] | None = None,
) -> list[str]:
    """Deduplicate and filter suggested questions for user-facing display."""
    current_norm = _normalize_text(current_question)
    seen: set[str] = set()
    filtered: list[str] = []

    for question in questions:
        text = _format_question(str(question or ""))
        norm = _normalize_text(text)
        if not norm or norm in seen:
            continue
        if len(norm) < 5 or len(norm) > 36:
            continue
        if current_norm and norm == current_norm:
            continue
        if any(generic in norm for generic in GENERIC_QUESTIONS):
            continue
        if any(term in norm for term in UNSAFE_TERMS):
            continue
        seen.add(norm)
        filtered.append(text)
        if len(filtered) >= limit:
            return filtered

    fallback_pool = list(fallback or []) + DEFAULT_POOL
    for question in fallback_pool:
        text = _format_question(question)
        norm = _normalize_text(text)
        if norm and norm not in seen and norm != current_norm:
            seen.add(norm)
            filtered.append(text)
        if len(filtered) >= limit:
            break

    return filtered[:limit]


class SuggestedQuestionService:
    """Build dynamic suggestions from profile, recent chat, and semantic memory."""

    async def get_home_suggestions(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        limit: int = 3,
    ) -> list[str]:
        profile, recent_messages, semantic_memories = await self._load_context(db, user_id)
        candidates = self._build_candidates(
            user_id=user_id,
            profile=profile,
            recent_messages=recent_messages,
            semantic_memories=semantic_memories,
        )
        ranked = sorted(candidates, key=lambda item: item.score, reverse=True)
        return filter_suggested_questions(
            [item.text for item in ranked],
            limit=limit,
            fallback=self._rotated_defaults(user_id),
        )

    async def record_feedback(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        question: str,
        action: str,
        source: str | None = None,
        context: dict | None = None,
    ) -> SuggestedQuestionFeedback:
        feedback = SuggestedQuestionFeedback(
            user_id=user_id,
            question=question[:200],
            action=action,
            source=source,
            context=context or {},
        )
        db.add(feedback)
        await db.commit()
        await db.refresh(feedback)
        return feedback

    async def _load_context(
        self,
        db: AsyncSession,
        user_id: str,
    ) -> tuple[dict, list[str], list[dict]]:
        profile = await profile_manager.load_profile(db, user_id)
        recent_messages = await self._load_recent_messages(db, user_id)
        semantic_memories: list[dict] = []
        try:
            semantic_memories = await long_term_memory.search_memories(
                user_id,
                "运动 饮食 睡眠 作息 健康目标 长期习惯",
                limit=5,
            )
        except Exception:
            logger.info("[suggestions] semantic memory unavailable; using profile and chat context")
        return profile, recent_messages, semantic_memories

    async def _load_recent_messages(
        self,
        db: AsyncSession,
        user_id: str,
        *,
        limit: int = 20,
    ) -> list[str]:
        result = await db.execute(
            select(ChatMessage.content)
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .where(ChatSession.user_id == user_id)
            .where(ChatMessage.role == "user")
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        return [str(content or "") for content in result.scalars().all() if content]

    def _build_candidates(
        self,
        *,
        user_id: str,
        profile: dict,
        recent_messages: list[str],
        semantic_memories: list[dict],
    ) -> list[SuggestedQuestion]:
        candidates: list[SuggestedQuestion] = []

        def add(text: str, score: float, source: str) -> None:
            candidates.append(SuggestedQuestion(text=text, score=score, source=source))

        goals = profile.get("health_goals") or []
        goal_text = " ".join(map(str, goals))
        health_status = profile.get("health_status") or {}
        lifestyle = profile.get("lifestyle") or {}
        diet = profile.get("diet_preferences") or {}
        context_text = " ".join(recent_messages + [str(memory.get("content", "")) for memory in semantic_memories])

        if any(term in goal_text for term in ("减脂", "减肥", "控糖", "增肌")):
            add("结合我的目标给一份饮食和运动计划", 0.95, "profile_goal")
        if any(term in goal_text for term in ("改善睡眠", "调作息")):
            add("根据我的睡眠情况怎么调整作息", 0.94, "profile_goal")

        allergies = health_status.get("allergies") or health_status.get("allergy") or []
        conditions = health_status.get("conditions") or health_status.get("chronic_diseases") or []
        if allergies or diet.get("avoid"):
            add("结合我的忌口给一份饮食建议", 0.9, "profile_diet")
        if conditions:
            add("结合我的健康状况运动时要注意什么", 0.88, "profile_risk")

        if any(term in str(lifestyle) for term in ("久坐", "加班", "通勤")):
            add("久坐和加班时怎么安排轻量运动", 0.86, "profile_lifestyle")

        if any(term in context_text for term in ("跑步", "运动", "锻炼", "健身", "周末")):
            add("结合我的运动习惯安排本周计划", 0.84, "memory_exercise")
            add("如何判断我的运动强度是否合适", 0.78, "memory_exercise")
        if any(term in context_text for term in ("睡眠", "熬夜", "作息", "失眠", "早醒")):
            add("分析一下我最近的睡眠和作息", 0.83, "memory_sleep")
        if any(term in context_text for term in ("饮食", "早餐", "晚餐", "控糖", "低盐", "夜宵")):
            add("帮我看看最近饮食有哪些可调整点", 0.82, "memory_nutrition")
        if any(term in context_text for term in ("天气", "空气", "跑步", "户外")):
            add("今天的天气适合户外运动吗", 0.76, "context_environment")

        for index, text in enumerate(self._rotated_defaults(user_id)):
            add(text, 0.5 - index * 0.01, "default")

        return candidates

    def _rotated_defaults(self, user_id: str) -> list[str]:
        digest = hashlib.sha256(str(user_id or "").encode("utf-8")).hexdigest()
        offset = int(digest[:4], 16) % len(DEFAULT_POOL)
        return DEFAULT_POOL[offset:] + DEFAULT_POOL[:offset]


suggested_question_service = SuggestedQuestionService()