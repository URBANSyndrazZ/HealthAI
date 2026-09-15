import importlib
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.models import ChatMessage, ChatSession, ChatSessionSummary
from app.models.database import Base

medium_term_module = importlib.import_module("app.memory.medium_term")
load_context_module = importlib.import_module(
    "app.agents.health_advisor.nodes.load_context"
)
generate_response_module = importlib.import_module(
    "app.agents.health_advisor.nodes.generate_response"
)


class FakeLLM:
    def __init__(self, response="滚动摘要", error=None):
        self.response = response
        self.error = error
        self.prompts = []

    async def chat(self, system_prompt: str, user_message: str, **kwargs):
        if self.error:
            raise self.error
        self.prompts.append(user_message)
        return self.response


def create_test_session_factory():
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
    )
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def seed_messages(session_factory, count: int, session_id: str = "session"):
    async with session_factory() as db:
        db.add(ChatSession(id=session_id, user_id="user"))
        base_time = datetime(2026, 1, 1, 12, 0)
        for index in range(count):
            db.add(
                ChatMessage(
                    id=f"m{index:02d}",
                    session_id=session_id,
                    role="user" if index % 2 == 0 else "assistant",
                    content=f"message {index}",
                    created_at=base_time + timedelta(minutes=index),
                )
            )
        await db.commit()


@pytest.mark.anyio
async def test_summary_is_created_for_messages_outside_recent_window(monkeypatch):
    engine, session_factory = create_test_session_factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_messages(session_factory, 12)

    llm = FakeLLM(response="用户希望控制体重，并计划逐步增加运动。")
    monkeypatch.setattr(medium_term_module, "async_session", session_factory)
    monkeypatch.setattr(medium_term_module, "deepseek_client", llm)

    updated = await medium_term_module.medium_term_memory.update_summary("session")
    assert updated is True

    async with session_factory() as db:
        summary = (
            await db.execute(select(ChatSessionSummary).where(ChatSessionSummary.session_id == "session"))
        ).scalar_one()
        assert summary.summary.startswith("用户希望")
        assert summary.covered_until_message_id == "m03"
        assert summary.covered_message_count == 4
        assert summary.version == 0
    assert "[user] message 0" in llm.prompts[0]
    assert "[assistant] message 11" not in llm.prompts[0]
    await engine.dispose()


@pytest.mark.anyio
async def test_summary_is_not_created_below_trigger_threshold(monkeypatch):
    engine, session_factory = create_test_session_factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_messages(session_factory, 11)

    llm = FakeLLM()
    monkeypatch.setattr(medium_term_module, "async_session", session_factory)
    monkeypatch.setattr(medium_term_module, "deepseek_client", llm)

    updated = await medium_term_module.medium_term_memory.update_summary("session")
    assert updated is False
    assert llm.prompts == []
    await engine.dispose()


@pytest.mark.anyio
async def test_llm_failure_preserves_existing_summary(monkeypatch):
    engine, session_factory = create_test_session_factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_messages(session_factory, 12)

    async with session_factory() as db:
        db.add(
            ChatSessionSummary(
                session_id="session",
                summary="旧摘要",
                covered_until_message_id="m01",
                covered_message_count=2,
                version=2,
            )
        )
        await db.commit()

    llm = FakeLLM(error=RuntimeError("LLM unavailable"))
    monkeypatch.setattr(medium_term_module, "async_session", session_factory)
    monkeypatch.setattr(medium_term_module, "deepseek_client", llm)

    updated = await medium_term_module.medium_term_memory.update_summary("session")
    assert updated is False

    async with session_factory() as db:
        summary = (
            await db.execute(select(ChatSessionSummary).where(ChatSessionSummary.session_id == "session"))
        ).scalar_one()
        assert summary.summary == "旧摘要"
        assert summary.version == 2
    await engine.dispose()


@pytest.mark.anyio
async def test_stale_version_does_not_overwrite_newer_summary(monkeypatch):
    engine, session_factory = create_test_session_factory()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await seed_messages(session_factory, 12)

    async with session_factory() as db:
        db.add(
            ChatSessionSummary(
                session_id="session",
                summary="旧摘要",
                covered_message_count=0,
                version=5,
            )
        )
        await db.commit()

    memory = medium_term_module.MediumTermMemory()
    monkeypatch.setattr(medium_term_module, "async_session", session_factory)
    snapshot = await memory._collect_summary_input("session")
    assert snapshot is not None

    async with session_factory() as db:
        summary = (
            await db.execute(select(ChatSessionSummary).where(ChatSessionSummary.session_id == "session"))
        ).scalar_one()
        summary.version = 6
        summary.summary = "并发更新的新摘要"
        await db.commit()

    persisted = await memory._persist_summary("session", "过期摘要", snapshot)
    assert persisted is False

    async with session_factory() as db:
        summary = (
            await db.execute(select(ChatSessionSummary).where(ChatSessionSummary.session_id == "session"))
        ).scalar_one()
        assert summary.summary == "并发更新的新摘要"
        assert summary.version == 6
    await engine.dispose()


@pytest.mark.anyio
async def test_load_context_exposes_medium_term_summary(monkeypatch):
    class ShortMemory:
        async def get_history(self, user_id, session_id):
            return [{"role": "user", "message": "最近消息"}]

        async def hydrate_from_db(self, user_id, session_id, history):
            return None

    class MediumMemory:
        async def get_summary(self, db, session_id):
            return "会话摘要"

    class Result:
        def scalars(self):
            class Scalar:
                def all(self):
                    return []

            return Scalar()

    class Db:
        async def execute(self, query):
            return Result()

    monkeypatch.setattr(load_context_module, "short_term_memory", ShortMemory())
    monkeypatch.setattr(load_context_module, "medium_term_memory", MediumMemory())

    state = {"user_id": "user", "session_id": "session", "context": {}}
    updated = await load_context_module.load_context(state, Db())
    assert updated["context"]["medium_term_summary"] == "会话摘要"


@pytest.mark.anyio
async def test_generate_response_renders_medium_term_summary(monkeypatch):
    captured = {}

    class LLM:
        async def chat(self, system_prompt: str, user_message: str, **kwargs):
            captured["prompt"] = user_message
            return "好的，我可以继续协助。"

    state = {
        "user_message": "请继续刚才的话题。",
        "intent": "general",
        "context": {"medium_term_summary": "用户正在讨论控糖目标。"},
        "memory_policy": {"needs_short_term": False, "needs_long_term": False, "needs_rag": False},
    }
    monkeypatch.setattr(generate_response_module, "deepseek_client", LLM())

    updated = await generate_response_module.generate_response(state)
    assert updated["response"] == "好的，我可以继续协助。"
    assert "当前会话进展摘要" in captured["prompt"]
    assert "用户正在讨论控糖目标。" in captured["prompt"]
