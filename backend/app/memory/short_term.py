import json
import logging
from collections import defaultdict
from typing import Any, Protocol

from redis.asyncio import Redis

from app.config import settings

logger = logging.getLogger(__name__)


class ShortTermMemoryBackend(Protocol):
    async def add_turn(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        assistant_message: str,
        *,
        message_id: str | None = None,
        created_at: str | None = None,
    ) -> None: ...

    async def get_history(self, user_id: str, session_id: str) -> list[dict[str, Any]]: ...

    async def hydrate_from_db(
        self,
        user_id: str,
        session_id: str,
        history: list[dict[str, Any]],
    ) -> None: ...

    async def clear(self, user_id: str, session_id: str) -> None: ...

    async def close(self) -> None: ...


class InMemoryShortTermMemory:
    """Process-local backend for development and tests."""

    def __init__(self, max_messages: int | None = None):
        self.max_messages = max(2, max_messages or settings.short_term_max_messages)
        self._store: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    async def add_turn(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        assistant_message: str,
        *,
        message_id: str | None = None,
        created_at: str | None = None,
    ) -> None:
        key = (user_id, session_id)
        messages = self._store[key]
        messages.extend(
            [
                {"role": "user", "message": user_message},
                {"role": "assistant", "message": assistant_message},
            ]
        )
        self._store[key] = messages[-self.max_messages:]

    async def get_history(self, user_id: str, session_id: str) -> list[dict[str, Any]]:
        return list(self._store.get((user_id, session_id), []))

    async def hydrate_from_db(
        self,
        user_id: str,
        session_id: str,
        history: list[dict[str, Any]],
    ) -> None:
        self._store[(user_id, session_id)] = [
            {"role": str(item.get("role")), "message": str(item.get("message") or item.get("content") or "")}
            for item in history[-self.max_messages:]
        ]

    async def clear(self, user_id: str, session_id: str) -> None:
        self._store.pop((user_id, session_id), None)

    async def close(self) -> None:
        return None


class RedisShortTermMemory:
    """Redis-backed shared short-term memory."""

    def __init__(
        self,
        *,
        max_messages: int | None = None,
        ttl_seconds: int | None = None,
        key_prefix: str | None = None,
        client: Redis | None = None,
    ):
        self.max_messages = max(2, max_messages or settings.short_term_max_messages)
        self.ttl_seconds = max(1, ttl_seconds or settings.short_term_ttl_seconds)
        self.key_prefix = key_prefix or settings.short_term_key_prefix
        self._client: Redis | None = client

    def _key(self, user_id: str, session_id: str) -> str:
        return f"{self.key_prefix}:user:{user_id}:session:{session_id}"

    async def _get_client(self) -> Redis:
        if self._client is None:
            self._client = Redis.from_url(
                f"redis://{settings.redis_host}:{settings.redis_port}/{settings.redis_db}",
                password=settings.redis_password,
                decode_responses=True,
                socket_timeout=settings.short_term_redis_socket_timeout,
                socket_connect_timeout=settings.short_term_redis_connect_timeout,
            )
        return self._client

    async def add_turn(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        assistant_message: str,
        *,
        message_id: str | None = None,
        created_at: str | None = None,
    ) -> None:
        if not user_id or not session_id:
            return
        client = await self._get_client()
        key = self._key(user_id, session_id)
        async with client.pipeline(transaction=True) as pipeline:
            pipeline.rpush(
                key,
                json.dumps({"role": "user", "message": user_message}, ensure_ascii=False),
                json.dumps(
                    {
                        "role": "assistant",
                        "message": assistant_message,
                        "message_id": message_id or "",
                        "created_at": created_at or "",
                    },
                    ensure_ascii=False,
                ),
            )
            pipeline.ltrim(key, -self.max_messages, -1)
            pipeline.expire(key, self.ttl_seconds)
            await pipeline.execute()

    async def get_history(self, user_id: str, session_id: str) -> list[dict[str, Any]]:
        if not user_id or not session_id:
            return []
        client = await self._get_client()
        raw_messages = await client.lrange(self._key(user_id, session_id), -self.max_messages, -1)
        messages: list[dict[str, Any]] = []
        for raw_message in raw_messages:
            try:
                message = json.loads(raw_message)
            except (TypeError, json.JSONDecodeError):
                logger.warning("Ignoring invalid short-term memory entry")
                continue
            if isinstance(message, dict) and message.get("role") in {"user", "assistant"}:
                messages.append(message)
        return messages

    async def hydrate_from_db(
        self,
        user_id: str,
        session_id: str,
        history: list[dict[str, Any]],
    ) -> None:
        if not user_id or not session_id or not history:
            return
        raw_messages = [
            json.dumps(
                {
                    "role": str(item.get("role")),
                    "message": str(item.get("message") or item.get("content") or ""),
                    "message_id": str(item.get("id") or ""),
                    "created_at": str(item.get("created_at") or ""),
                },
                ensure_ascii=False,
            )
            for item in history[-self.max_messages:]
        ]
        client = await self._get_client()
        key = self._key(user_id, session_id)
        async with client.pipeline(transaction=True) as pipeline:
            pipeline.delete(key)
            pipeline.rpush(key, *raw_messages)
            pipeline.expire(key, self.ttl_seconds)
            await pipeline.execute()

    async def clear(self, user_id: str, session_id: str) -> None:
        if not user_id or not session_id:
            return
        client = await self._get_client()
        await client.delete(self._key(user_id, session_id))

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None


def create_short_term_memory() -> ShortTermMemoryBackend:
    if settings.short_term_backend == "redis":
        return RedisShortTermMemory()
    return InMemoryShortTermMemory()


short_term_memory: ShortTermMemoryBackend = create_short_term_memory()
