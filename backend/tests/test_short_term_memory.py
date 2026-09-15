import json

import pytest

import importlib

load_context_module = importlib.import_module(
    "app.agents.health_advisor.nodes.load_context"
)
load_context = load_context_module.load_context
from app.memory.short_term import InMemoryShortTermMemory, RedisShortTermMemory


class FakePipeline:
    def __init__(self):
        self.commands = []

    def rpush(self, key, *values):
        self.commands.append(("rpush", key, values))

    def ltrim(self, key, start, end):
        self.commands.append(("ltrim", key, start, end))

    def expire(self, key, ttl):
        self.commands.append(("expire", key, ttl))

    def delete(self, key):
        self.commands.append(("delete", key))

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return None

    async def execute(self):
        return []


class FakeRedis:
    def __init__(self, values=None):
        self.values = values or []
        self.error = None
        self.ranges = 0

    def pipeline(self, transaction=True):
        return FakePipeline()

    async def lrange(self, key, start, end):
        self.ranges += 1
        if self.error:
            raise self.error
        return self.values


@pytest.mark.anyio
async def test_in_memory_backend_bounds_and_normalizes_history():
    memory = InMemoryShortTermMemory(max_messages=4)
    await memory.add_turn("user", "session", "u1", "a1")
    await memory.add_turn("user", "session", "u2", "a2")
    await memory.add_turn("user", "session", "u3", "a3")

    history = await memory.get_history("user", "session")
    assert [item["message"] for item in history] == ["u2", "a2", "u3", "a3"]

    await memory.hydrate_from_db(
        "user", "session", [{"role": "user", "content": "db", "id": "m1", "created_at": "now"}]
    )
    assert await memory.get_history("user", "session") == [{"role": "user", "message": "db"}]


@pytest.mark.anyio
async def test_redis_add_turn_uses_atomic_pipeline():
    client = FakeRedis()
    memory = RedisShortTermMemory(max_messages=4, ttl_seconds=60, client=client)

    await memory.add_turn("user", "session", "hello", "answer", message_id="m2", created_at="now")

    memory.key_prefix = "prefix"
    key = memory._key("user", "session")
    assert key == "prefix:user:user:session:session"


@pytest.mark.anyio
async def test_redis_get_history_ignores_invalid_entries():
    client = FakeRedis([json.dumps({"role": "user", "message": "ok"}), "{bad"])
    memory = RedisShortTermMemory(max_messages=4, client=client)
    memory.key_prefix = "prefix"

    history = await memory.get_history("user", "session")
    assert history == [{"role": "user", "message": "ok"}]


@pytest.mark.anyio
async def test_load_context_rebuilds_missing_history_from_database(monkeypatch):
    class Backend:
        async def get_history(self, user_id, session_id):
            return []

        async def hydrate_from_db(self, user_id, session_id, history):
            self.hydrated = history

    class Message:
        id = "m1"
        role = "user"
        content = "database history"

        @property
        def created_at(self):
            return None

    class Result:
        def scalars(self):
            class Scalar:
                def all(self):
                    return [Message()]

            return Scalar()

    class Db:
        async def execute(self, query):
            return Result()

    backend = Backend()
    monkeypatch.setattr(load_context_module, "short_term_memory", backend)

    state = {"user_id": "user", "session_id": "session", "context": {}}
    updated = await load_context(state, Db())

    assert backend.hydrated == [
        {"id": "m1", "role": "user", "message": "database history", "created_at": ""}
    ]
    assert updated["context"]["short_term_history"] == backend.hydrated


@pytest.mark.anyio
async def test_load_context_degrades_when_backend_fails(monkeypatch):
    class Backend:
        async def get_history(self, user_id, session_id):
            raise RuntimeError("redis unavailable")

    class Message:
        id = "m1"
        role = "user"
        content = "database history"

        @property
        def created_at(self):
            return None

    class Result:
        def scalars(self):
            class Scalar:
                def all(self):
                    return [Message()]

            return Scalar()

    class Db:
        async def execute(self, query):
            return Result()

    monkeypatch.setattr(load_context_module, "short_term_memory", Backend())
    state = {"user_id": "user", "session_id": "session", "context": {}}
    updated = await load_context(state, Db())

    assert updated["context"]["short_term_history"] == [
        {"id": "m1", "role": "user", "message": "database history", "created_at": ""}
    ]
