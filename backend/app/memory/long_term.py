"""Long-term memory backed by Elasticsearch dense-vector retrieval."""
import asyncio
from datetime import timedelta
import hashlib
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.time import utc_isoformat, utc_now_naive
from app.llm.deepseek import deepseek_client
from app.models.chat import ChatMessage, ChatSession
from app.rag.embeddings import EmbeddingModel

logger = logging.getLogger(__name__)


def _is_vector_dimension_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "different dimension" in message or "query vector has a different dimension" in message


MEMORY_STOP_TERMS = {
    "什么",
    "时候",
    "怎么",
    "一下",
    "请问",
    "最近",
    "今天",
    "可以",
    "是否",
    "一般",
    "通常",
    "帮我",
    "一下子",
    "告诉",
    "这个",
    "那个",
}

FIRST_PERSON_MARKERS = ("我", "我的", "自己", "平时", "一般", "通常", "经常", "习惯")
IMPLICIT_MEMORY_CUES = ("有时候", "最近", "基本", "总是", "容易", "不太", "比较", "一忙", "常常")

EXERCISE_KEYWORDS = ("运动", "跑步", "锻炼", "健身", "游泳", "骑行", "散步")
EXERCISE_ACTIVITY_TYPES = ("跑步", "慢跑", "快走", "散步", "游泳", "骑行", "羽毛球", "篮球", "足球", "跳绳", "瑜伽", "力量训练", "爬山", "徒步", "健身")
TIME_PREFERENCE_WORDS = ("周末", "工作日", "早上", "上午", "中午", "下午", "傍晚", "晚上", "夜间", "清晨")
DIET_CONSTRAINT_TERMS = {
    "低盐": ("低盐", 0.92),
    "控糖": ("控糖", 0.92),
    "低糖": ("低糖", 0.9),
    "低脂": ("低脂", 0.88),
    "控碳水": ("控碳水", 0.9),
    "少油": ("少油", 0.84),
    "少辣": ("少辣", 0.8),
    "素食": ("素食", 0.9),
    "清淡": ("清淡", 0.82),
}
MEAL_PATTERN_RULES = (
    ("不吃早餐", "经常不吃早餐", 0.88),
    ("早餐不吃", "经常不吃早餐", 0.88),
    ("夜宵", "夜宵频繁", 0.82),
    ("晚饭吃得晚", "晚饭通常较晚", 0.8),
    ("晚餐吃得晚", "晚饭通常较晚", 0.8),
)
SLEEP_PATTERN_RULES = (
    ("熬夜", "经常熬夜", 0.88),
    ("补觉", "周末补觉", 0.78),
    ("午睡", "有午睡习惯", 0.76),
)
LIFESTYLE_CONSTRAINT_RULES = (
    ("工作日没时间运动", "工作日可用于运动的时间较少", 0.9),
    ("经常加班", "经常加班", 0.84),
    ("久坐", "久坐较多", 0.82),
    ("通勤时间很长", "通勤时间较长", 0.78),
)
DAY_PREFERENCE_ALIASES = {
    "星期一": "周一",
    "星期二": "周二",
    "星期三": "周三",
    "星期四": "周四",
    "星期五": "周五",
    "星期六": "周六",
    "星期日": "周日",
    "星期天": "周日",
    "礼拜一": "周一",
    "礼拜二": "周二",
    "礼拜三": "周三",
    "礼拜四": "周四",
    "礼拜五": "周五",
    "礼拜六": "周六",
    "礼拜日": "周日",
    "礼拜天": "周日",
    "周天": "周日",
}
GOAL_WORDS = ("减脂", "减重", "增肌", "控糖", "控压", "降压", "改善睡眠", "调作息")
CONDITION_WORDS = ("高血压", "糖尿病", "高血脂", "哮喘", "痛风", "胃病", "失眠")
STRUCTURED_PROFILE_MEMORY_TYPES = {"profile", "allergy", "condition", "goal"}
STRUCTURED_PROFILE_SLOTS = {"age", "gender", "allergy", "condition", "health_condition", "health_goal"}
DOMAIN_KEYWORDS = {
    "exercise": EXERCISE_KEYWORDS + ("力量训练", "慢跑"),
    "nutrition": ("饮食", "吃", "早餐", "晚饭", "夜宵", "燕麦", "鸡蛋", "牛奶", "香菜", "低盐", "控糖", "素食"),
    "sleep": ("睡", "作息", "熬夜", "午睡", "补觉", "起床"),
    "lifestyle": ("工作日", "加班", "久坐", "通勤"),
    "general_health": GOAL_WORDS + CONDITION_WORDS,
}
MEMORY_SOURCE_FIELDS = [
    "id",
    "user_id",
    "session_id",
    "domain",
    "content",
    "source_message",
    "memory_type",
    "topic",
    "slot",
    "value",
    "confidence",
    "evidence",
    "tags",
    "salience",
    "created_at",
    "updated_at",
]


class LongTermMemory:
    """Elasticsearch-backed long-term semantic memory with DB fallback."""

    def __init__(self) -> None:
        self.index_name = settings.memory_index_name
        self.top_k = settings.memory_top_k
        self.candidate_k = settings.memory_candidate_k
        self.vector_weight = settings.memory_vector_weight
        self.bm25_weight = settings.memory_bm25_weight
        self.max_days = settings.memory_max_days
        self._client = None
        self._embedding_model: EmbeddingModel | None = None

    async def initialize(self) -> None:
        """Create the memory index if Elasticsearch is configured."""
        if not settings.elasticsearch_url:
            return
        await self._connect()
        await self._ensure_index()

    async def close(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def get_recent_messages(
        self,
        db: AsyncSession,
        user_id: str,
        days: int = 30,
        limit: int = 50,
        exclude_session_id: str | None = None,
    ) -> list[dict]:
        cutoff = utc_now_naive() - timedelta(days=days)
        stmt = (
            select(ChatMessage)
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .where(ChatSession.user_id == user_id)
            .where(ChatMessage.created_at >= cutoff)
            .order_by(ChatMessage.created_at.desc())
            .limit(limit)
        )
        if exclude_session_id:
            stmt = stmt.where(ChatSession.id != exclude_session_id)
        result = await db.execute(stmt)
        messages = result.scalars().all()
        return [
            {"role": m.role, "content": m.content, "created_at": utc_isoformat(m.created_at)}
            for m in reversed(messages)
        ]

    """
    搜索相关消息的过程：
    1. 使用elasticsearch搜索相关消息
    2. 若elasticsearch搜索失败，则使用DB搜索
    3. 返回搜索结果list
    """
    async def search_relevant_messages(
        self,
        db: AsyncSession,
        user_id: str,
        query: str,
        *,
        days: int = 180,
        candidate_limit: int = 120,
        limit: int = 8,
        exclude_session_id: str | None = None,
    ) -> list[dict]:
        if settings.elasticsearch_url:
            try:
                memories = await self.search_memories(user_id, query, limit=limit)
                if memories:
                    logger.info("[long_term_memory] retrieved %d semantic memories from ES", len(memories))
                    return memories
            except Exception:
                logger.exception("[long_term_memory] semantic memory search failed, falling back to DB")

        return await self._fallback_keyword_search(
            db,
            user_id,
            query,
            days=days,
            candidate_limit=candidate_limit,
            limit=limit,
            exclude_session_id=exclude_session_id,
        )

    """
    搜索elasticsearch数据库记忆的过程：
    1.将query进行向量化，用于稠密向量搜索
    2.执行BM25（关键词搜索）+KNN搜索(稠密向量搜索)
    3.将检索到的top_k/size结果进行RRF混合排序
    4.最后返回top_k/size条去噪的list结果
    """
    async def search_memories(
        self,
        user_id: str,
        query: str,
        *,
        limit: int | None = None,
    ) -> list[dict]:
        """Search the ES long-term memory index with vector + BM25 hybrid retrieval."""
        if not settings.elasticsearch_url or not user_id or not str(query or "").strip():
            return []

        await self.initialize()
        # asyncio.to_thread在后台线程执行同步阻塞函数，由于encode是同步方法，避免阻塞事件循环
        query_vector = await asyncio.to_thread(self._embedding_model_instance().encode, query)
        query_vector = query_vector[0]

        size = limit or self.top_k
        bm25_results, vector_results = await asyncio.gather(
            self._bm25_search_memories(user_id, query, size),
            self._vector_search_memories(user_id, query_vector, size),
        )

        fused = self._fuse_ranked_results(
            [
                ("bm25", bm25_results, self.bm25_weight),
                ("vector", vector_results, self.vector_weight),
            ]
        )
        return self._denoise_memories(fused, limit=size)

    async def store_user_message_memories(
        self,
        user_id: str,
        session_id: str,
        user_message: str,
        assistant_response: str = "",
        extracted_profile: dict | None = None,
    ) -> list[str]:
        """Extract stable user facts/preferences and upsert them into ES."""
        if not settings.memory_write_enabled or not settings.elasticsearch_url:
            return []
        if not user_id or not session_id:
            return []

        memory_docs = self.extract_memories(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            assistant_response=assistant_response,
            extracted_profile=extracted_profile or {},
        )
        memory_docs = await self._maybe_supplement_memories_with_llm(
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            assistant_response=assistant_response,
            existing_docs=memory_docs,
        )
        if not memory_docs:
            return []

        return await self.add_memory_documents(memory_docs)

    def extract_memories(
        self,
        *,
        user_id: str,
        session_id: str,
        user_message: str,
        assistant_response: str = "",
        extracted_profile: dict | None = None,
    ) -> list[dict]:
        """Extract stable personal facts from the user's message."""
        normalized = re.sub(r"\s+", " ", str(user_message or "")).strip()
        if len(normalized) < 4:
            return []

        docs: list[dict] = []
        seen: set[str] = set()

        def add_memory(
            *,
            content: str,
            memory_type: str,
            topic: str,
            salience: float,
            confidence: float = 0.85,
            domain: str | None = None,
            slot: str | None = None,
            value: str | None = None,
            evidence: str | None = None,
            tags: list[str] | None = None,
        ) -> None:
            content = str(content or "").strip()
            if not content:
                return
            slot = slot or topic
            evidence = evidence or normalized
            dedupe_key = f"{memory_type}::{topic}::{slot}::{value or content}"
            if dedupe_key in seen:
                return
            seen.add(dedupe_key)
            docs.append(
                {
                    "id": self._stable_memory_id(user_id, memory_type, topic, content),
                    "user_id": user_id,
                    "session_id": session_id,
                    "domain": domain or self._infer_domain_from_topic(topic),
                    "content": content,
                    "source_message": normalized,
                    "assistant_response": assistant_response[:800],
                    "memory_type": memory_type,
                    "topic": topic,
                    "slot": slot,
                    "value": value or content,
                    "confidence": confidence,
                    "evidence": evidence,
                    "tags": tags or [topic],
                    "salience": salience,
                    "created_at": utc_isoformat(),
                    "updated_at": utc_isoformat(),
                }
            )

        self._extract_exercise_memories(normalized, add_memory)
        self._extract_diet_memories(normalized, add_memory)
        self._extract_sleep_memories(normalized, add_memory)
        self._extract_lifestyle_memories(normalized, add_memory)

        return docs

    async def _maybe_supplement_memories_with_llm(
        self,
        *,
        user_id: str,
        session_id: str,
        user_message: str,
        assistant_response: str,
        existing_docs: list[dict],
    ) -> list[dict]:
        """Use LLM to supplement rule extraction when the message is complex or implicit."""
        if not self._should_call_llm_supplement(user_message, existing_docs):
            return existing_docs

        prompt = self._build_llm_supplement_prompt(user_message, existing_docs)
        try:
            result = await deepseek_client.json_chat(
                system_prompt=(
                    "你是健康管理系统的长期记忆抽取器。"
                    "请只抽取稳定、跨会话可复用、对后续个性化建议有帮助的用户事实。"
                    "不要抽取一次性的短期状态、寒暄、模糊情绪。"
                    "返回严格 JSON。"
                ),
                user_message=prompt,
            )
        except Exception:
            logger.exception("[long_term_memory] LLM supplement extraction failed")
            return existing_docs

        memories = result.get("memories") if isinstance(result, dict) else None
        if not isinstance(memories, list):
            return existing_docs

        merged_docs = list(existing_docs)
        seen = {
            self._memory_dedupe_key(
                memory_type=str(doc.get("memory_type") or ""),
                topic=str(doc.get("topic") or ""),
                slot=str(doc.get("slot") or doc.get("topic") or ""),
                value=str(doc.get("value") or doc.get("content") or ""),
            )
            for doc in merged_docs
        }

        for item in memories:
            normalized_doc = self._normalize_llm_memory_item(
                user_id=user_id,
                session_id=session_id,
                user_message=user_message,
                assistant_response=assistant_response,
                item=item,
            )
            if not normalized_doc:
                continue
            dedupe_key = self._memory_dedupe_key(
                memory_type=normalized_doc["memory_type"],
                topic=normalized_doc["topic"],
                slot=normalized_doc["slot"],
                value=str(normalized_doc["value"]),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            merged_docs.append(normalized_doc)

        return merged_docs

    def _should_call_llm_supplement(self, user_message: str, existing_docs: list[dict]) -> bool:
        if not settings.memory_use_llm_supplement:
            return False

        normalized = re.sub(r"\s+", " ", str(user_message or "")).strip()
        if len(normalized) < 10:
            return False

        has_first_person = any(marker in normalized for marker in FIRST_PERSON_MARKERS)
        mentioned_domains = self._mentioned_domains(normalized)
        if not has_first_person or not mentioned_domains:
            return False

        rule_count = len(existing_docs)
        multi_domain = len(mentioned_domains) >= 2
        long_message = len(normalized) >= 24
        has_implicit_cue = any(marker in normalized for marker in IMPLICIT_MEMORY_CUES)

        return (
            rule_count == 0
            or multi_domain
            or (long_message and rule_count <= 1)
            or (has_implicit_cue and rule_count <= 2)
        )

    def _build_llm_supplement_prompt(self, user_message: str, existing_docs: list[dict]) -> str:
        extracted_facts = "\n".join(
            f"- {doc.get('content', '')}" for doc in existing_docs[:8] if doc.get("content")
        ) or "无"
        return f"""
请从下面这条用户消息中，补充抽取适合写入长期记忆的稳定信息。

用户消息：
{user_message}

规则已经抽取到的事实：
{extracted_facts}

要求：
1. 只补充规则未覆盖或规则不完整的长期事实
2. 只抽取稳定、跨会话可复用的信息
3. 不要抽取一次性的短期状态、泛泛抱怨、模糊情绪
4. 不要返回年龄、性别、过敏、慢病等结构化画像字段，这些字段写入 PostgreSQL 用户画像
5. 输出 JSON，格式如下：
{{
  "memories": [
    {{
      "domain": "exercise|nutrition|sleep|lifestyle|general_health",
      "topic": "如 diet_constraint / meal_pattern / sleep_time",
      "memory_type": "habit|constraint|preference",
      "slot": "结构化槽位名",
      "value": "规范化后的核心值",
      "content": "一条可读的中文事实，例如：用户饮食约束包含低盐。",
      "confidence": 0.0,
      "salience": 0.0,
      "evidence": "来自原句的证据",
      "tags": ["标签1", "标签2"]
    }}
  ]
}}

如果没有适合补充的长期记忆，返回 {{"memories": []}}。
""".strip()

    def _normalize_llm_memory_item(
        self,
        *,
        user_id: str,
        session_id: str,
        user_message: str,
        assistant_response: str,
        item: Any,
    ) -> dict | None:
        if not isinstance(item, dict):
            return None

        domain = str(item.get("domain") or "").strip() or "general_health"
        topic = str(item.get("topic") or "").strip()
        memory_type = str(item.get("memory_type") or "").strip() or "fact"
        slot = str(item.get("slot") or topic).strip()
        value = str(item.get("value") or "").strip()
        content = str(item.get("content") or "").strip()
        evidence = str(item.get("evidence") or user_message).strip()
        tags = [str(tag).strip() for tag in (item.get("tags") or []) if str(tag).strip()]
        confidence = self._clamp_score(item.get("confidence"), default=0.78)
        salience = self._clamp_score(item.get("salience"), default=0.82)

        if not topic or not slot:
            return None
        if memory_type in STRUCTURED_PROFILE_MEMORY_TYPES or slot in STRUCTURED_PROFILE_SLOTS:
            return None
        if confidence < 0.7:
            return None
        if not value:
            value = self._extract_value_from_content(content)
        if not content:
            content = self._build_content_from_slot(slot, value or evidence)
        if not value or not content:
            return None

        return {
            "id": self._stable_memory_id(user_id, memory_type, topic, content),
            "user_id": user_id,
            "session_id": session_id,
            "domain": domain,
            "content": content,
            "source_message": user_message,
            "assistant_response": assistant_response[:800],
            "memory_type": memory_type,
            "topic": topic,
            "slot": slot,
            "value": value,
            "confidence": confidence,
            "evidence": evidence,
            "tags": tags or [topic],
            "salience": salience,
            "created_at": utc_isoformat(),
            "updated_at": utc_isoformat(),
        }

    async def add_memory_documents(self, memory_docs: list[dict]) -> list[str]:
        if not memory_docs:
            return []

        await self.initialize()
        contents = [doc.get("content", "") for doc in memory_docs]
        embeddings = await asyncio.to_thread(self._embedding_model_instance().encode, contents)

        indexed_ids: list[str] = []
        for doc, embedding in zip(memory_docs, embeddings):
            content = doc.get("content", "")
            if not content:
                continue

            indexed_doc = {
                "id": doc.get("id"),
                "user_id": doc.get("user_id"),
                "session_id": doc.get("session_id"),
                "domain": doc.get("domain", "general_health"),
                "content": content,
                "source_message": doc.get("source_message", ""),
                "assistant_response": doc.get("assistant_response", ""),
                "memory_type": doc.get("memory_type", "fact"),
                "topic": doc.get("topic", "general"),
                "slot": doc.get("slot", doc.get("topic", "general")),
                "value": doc.get("value", content),
                "confidence": float(doc.get("confidence") or 0.75),
                "evidence": doc.get("evidence", doc.get("source_message", "")),
                "tags": doc.get("tags", []),
                "salience": float(doc.get("salience") or 0.5),
                "created_at": doc.get("created_at") or utc_isoformat(),
                "updated_at": utc_isoformat(),
                "embedding": embedding,
            }
            try:
                await self._client.index(
                    index=self.index_name,
                    id=doc["id"],
                    document=indexed_doc,
                )
            except Exception as exc:
                if not _is_vector_dimension_error(exc):
                    raise
                indexed_doc.pop("embedding", None)
                logger.warning(
                    "[long_term_memory] Skipping vector field while indexing %s because index %s has a different embedding dimension. "
                    "Memory remains searchable by BM25.",
                    doc["id"],
                    self.index_name,
                )
                await self._client.index(
                    index=self.index_name,
                    id=doc["id"],
                    document=indexed_doc,
                )
            indexed_ids.append(doc["id"])

        if indexed_ids:
            await self._client.indices.refresh(index=self.index_name)
        return indexed_ids

    async def _connect(self):
        if self._client is not None:
            return self._client

        try:
            from elasticsearch import AsyncElasticsearch
        except ImportError as exc:
            raise RuntimeError(
                "Elasticsearch async client is required for long-term vector memory."
            ) from exc

        kwargs: dict[str, Any] = {}
        if settings.elasticsearch_api_key:
            kwargs["api_key"] = settings.elasticsearch_api_key
        elif settings.elasticsearch_username and settings.elasticsearch_password:
            kwargs["basic_auth"] = (settings.elasticsearch_username, settings.elasticsearch_password)

        self._client = AsyncElasticsearch(settings.elasticsearch_url, **kwargs)
        return self._client

    async def _ensure_index(self) -> None:
        exists = await self._client.indices.exists(index=self.index_name)
        if exists:
            await self._warn_if_embedding_dimension_mismatch()
            return

        model_cfg = EmbeddingModel.MODELS.get(settings.rag_embedding_model, EmbeddingModel.MODELS["mock"])
        dimension = (
            settings.dashscope_embedding_dimension
            if model_cfg.get("provider") == "dashscope"
            else model_cfg["dimension"]
        )
        mapping = {
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "user_id": {"type": "keyword"},
                    "session_id": {"type": "keyword"},
                    "domain": {"type": "keyword"},
                    "content": {"type": "text"},
                    "source_message": {"type": "text"},
                    "assistant_response": {"type": "text"},
                    "memory_type": {"type": "keyword"},
                    "topic": {"type": "keyword"},
                    "slot": {"type": "keyword"},
                    "value": {"type": "keyword"},
                    "confidence": {"type": "float"},
                    "evidence": {"type": "text"},
                    "tags": {"type": "keyword"},
                    "salience": {"type": "float"},
                    "created_at": {"type": "date"},
                    "updated_at": {"type": "date"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": dimension,
                        "index": True,
                        "similarity": "cosine",
                    },
                }
            }
        }
        await self._client.indices.create(index=self.index_name, body=mapping)
        logger.info("[long_term_memory] created Elasticsearch index: %s", self.index_name)

    async def _warn_if_embedding_dimension_mismatch(self) -> None:
        model = self._embedding_model_instance()
        try:
            mapping = await self._client.indices.get_mapping(index=self.index_name)
            dims = (
                mapping.get(self.index_name, {})
                .get("mappings", {})
                .get("properties", {})
                .get("embedding", {})
                .get("dims")
            )
        except Exception:
            logger.debug("[long_term_memory] Failed to inspect index mapping for %s", self.index_name, exc_info=True)
            return

        if dims and int(dims) != model.dimension:
            logger.warning(
                "[long_term_memory] Elasticsearch index %s embedding dims=%s, current model dims=%s. "
                "Vector memory retrieval will be skipped until the index is rebuilt; BM25 retrieval remains available.",
                self.index_name,
                dims,
                model.dimension,
            )

    """
    BM25搜索记忆的过程：
    1. 构建body查询，包含过滤条件和多字段查询
    2. 执行BM25搜索
    3. 返回按格式封装的list搜索结果
    """
    async def _bm25_search_memories(self, user_id: str, query: str, limit: int) -> list[dict]:
        body = {
            "size": max(limit, self.candidate_k),
            "_source": MEMORY_SOURCE_FIELDS,
            "query": {
                # bool 组合查询、aggs 聚合查询、highlight 高亮匹配
                "bool": {
                    # 必须满足(不参与评分, 用于过滤)
                    "filter": [{"term": {"user_id": user_id}}],
                    # 必须满足(参与评分) =
                    "must": {
                        # 多字段查询
                        "multi_match": {
                            "query": query,
                            "fields": [
                                # ^N代表字段的权重
                                "content^4",
                                "source_message^2",
                                "domain^2",
                                "topic^2",
                                "slot^2",
                                "value^2",
                                "memory_type",
                            ],
                        }
                    },
                }
            },
        }
        response = await self._client.search(index=self.index_name, body=body)
        return [self._memory_hit_to_message(hit, "bm25") for hit in response["hits"]["hits"]]

    """
    KNN(向量搜索结果)
    """
    async def _vector_search_memories(
        self,
        user_id: str,
        query_vector: list[float],
        limit: int,
    ) -> list[dict]:
        body = {
            "size": max(limit, self.candidate_k),
            "_source": MEMORY_SOURCE_FIELDS,
            "knn": {
                "field": "embedding",
                "query_vector": query_vector,
                "k": max(limit, self.candidate_k),
                "num_candidates": max(self.candidate_k * 5, 60),
                "filter": {"term": {"user_id": user_id}},
            },
        }
        try:
            response = await self._client.search(index=self.index_name, body=body)
        except Exception as exc:
            if not _is_vector_dimension_error(exc):
                raise
            logger.warning(
                "[long_term_memory] Vector memory retrieval skipped for index=%s because query vector dims=%s do not match existing index mapping.",
                self.index_name,
                len(query_vector),
            )
            return []
        return [self._memory_hit_to_message(hit, "vector") for hit in response["hits"]["hits"]]

    def _fuse_ranked_results(
        self,
        ranked_lists: list[tuple[str, list[dict], float]],
    ) -> list[dict]:
        fused: dict[str, dict] = {}

        for retrieval_type, docs, weight in ranked_lists:
            for rank, doc in enumerate(docs, start=1):
                doc_id = doc["id"]
                rrf_score = weight / (60 + rank)
                if doc_id not in fused:
                    fused[doc_id] = {
                        **doc,
                        "score": 0.0,
                        "retrieval": {"sources": [], "raw_scores": {}},
                    }

                fused_doc = fused[doc_id]
                fused_doc["score"] += rrf_score
                fused_doc["retrieval"]["sources"].append(retrieval_type)
                fused_doc["retrieval"]["raw_scores"][retrieval_type] = doc.get("raw_score", 0.0)

        return sorted(fused.values(), key=lambda item: item["score"], reverse=True)

    def _memory_hit_to_message(self, hit: dict, retrieval_type: str) -> dict:
        source = hit.get("_source", {})
        return {
            "id": source.get("id") or hit.get("_id"),
            "role": "memory",
            "content": source.get("content", ""),
            "created_at": source.get("created_at"),
            "memory_type": source.get("memory_type"),
            "topic": source.get("topic"),
            "metadata": {
                "domain": source.get("domain"),
                "memory_type": source.get("memory_type"),
                "topic": source.get("topic"),
                "slot": source.get("slot"),
                "value": source.get("value"),
                "confidence": source.get("confidence"),
                "evidence": source.get("evidence"),
                "tags": source.get("tags") or [],
                "salience": source.get("salience"),
                "source_message": source.get("source_message"),
            },
            "raw_score": hit.get("_score", 0.0),
            "score": hit.get("_score", 0.0),
            "retrieval": {
                "sources": [retrieval_type],
                "raw_scores": {retrieval_type: hit.get("_score", 0.0)},
            },
        }

    async def _fallback_keyword_search(
        self,
        db: AsyncSession,
        user_id: str,
        query: str,
        *,
        days: int,
        candidate_limit: int,
        limit: int,
        exclude_session_id: str | None,
    ) -> list[dict]:
        messages = await self.get_recent_messages(
            db,
            user_id,
            days=days,
            limit=candidate_limit,
            exclude_session_id=exclude_session_id,
        )
        if not messages:
            return []

        terms = self._extract_query_terms(query)
        if not terms:
            return messages[-limit:]

        scored: list[tuple[float, dict]] = []
        for message in messages:
            content = str(message.get("content") or "")
            if not content:
                continue
            score = self._score_message(content, terms)
            if score <= 0:
                continue
            if message.get("role") == "user":
                score += 0.15
            scored.append((score, message))

        if not scored:
            return messages[-limit:]

        scored.sort(key=lambda item: item[0], reverse=True)
        top_messages = [message for _, message in scored[:limit]]
        top_messages.sort(key=lambda item: item.get("created_at", ""))
        return top_messages

    def _extract_query_terms(self, query: str) -> set[str]:
        normalized = re.sub(r"\s+", "", query or "")
        terms: set[str] = set()

        for token in re.findall(r"[A-Za-z0-9_]{2,}", normalized.lower()):
            terms.add(token)

        for run in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
            max_size = min(4, len(run))
            for size in range(2, max_size + 1):
                for index in range(0, len(run) - size + 1):
                    gram = run[index:index + size]
                    if gram not in MEMORY_STOP_TERMS:
                        terms.add(gram)

        domain_terms = (
            "运动",
            "跑步",
            "锻炼",
            "健身",
            "睡眠",
            "作息",
            "熬夜",
            "午睡",
            "饮食",
            "营养",
            "早餐",
            "夜宵",
            "忌口",
            "过敏",
            "高血压",
            "减脂",
            "增肌",
            "低盐",
            "控糖",
            "天气",
            "空气",
            "心率",
            "加班",
            "久坐",
        )
        for term in domain_terms:
            if term in normalized:
                terms.add(term)

        return {term for term in terms if term and term not in MEMORY_STOP_TERMS}

    def _score_message(self, content: str, terms: set[str]) -> float:
        score = 0.0
        for term in terms:
            if term in content:
                score += 1.0 + min(len(term), 4) * 0.2
        return score

    def _infer_domain_from_topic(self, topic: str) -> str:
        if topic.startswith("exercise"):
            return "exercise"
        if topic.startswith("diet") or topic == "allergy":
            return "nutrition"
        if topic.startswith("sleep"):
            return "sleep"
        if topic in {"lifestyle_constraint"}:
            return "lifestyle"
        if topic in {"basic_info"}:
            return "profile"
        return "general_health"

    def _mentioned_domains(self, text: str) -> set[str]:
        domains: set[str] = set()
        for domain, keywords in DOMAIN_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                domains.add(domain)
        return domains

    def _memory_dedupe_key(self, *, memory_type: str, topic: str, slot: str, value: str) -> str:
        return "::".join([memory_type, topic, slot, value])

    def _clamp_score(self, value: Any, *, default: float) -> float:
        try:
            score = float(value)
        except (TypeError, ValueError):
            return default
        return max(0.0, min(score, 1.0))

    def _extract_value_from_content(self, content: str) -> str:
        normalized = re.sub(r"^用户(?:的)?", "", str(content or "")).strip()
        normalized = normalized.replace("。", "").strip()
        if "包含" in normalized:
            return normalized.split("包含", 1)[1].strip(" ：:")
        if "是" in normalized:
            return normalized.split("是", 1)[1].strip(" ：:")
        if "为" in normalized:
            return normalized.split("为", 1)[1].strip(" ：:")
        return normalized

    def _build_content_from_slot(self, slot: str, value: str) -> str:
        templates = {
            "diet_constraint": f"用户饮食约束包含{value}。",
            "diet_preference": f"用户偏好{value}。",
            "diet_avoidance": f"用户饮食上不吃{value}。",
            "meal_pattern": f"用户的饮食模式表现为{value}。",
            "sleep_time": f"用户一般{value}。",
            "wake_time": f"用户一般{value}。",
            "sleep_pattern": f"用户的睡眠习惯表现为{value}。",
            "exercise_time": f"用户习惯{value}运动。",
            "exercise_activity": f"用户常进行的运动项目是{value}。",
            "exercise_frequency": f"用户一般{value}运动。",
            "health_goal": f"用户当前健康目标包含{value}。",
            "condition": f"用户提到自己有{value}。",
            "allergy": f"用户对{value}过敏。",
            "lifestyle_constraint": f"用户的生活方式约束包括{value}。",
        }
        return templates.get(slot, f"用户的长期记忆信息包括{value}。")

    def _extract_exercise_memories(self, text: str, add_memory) -> None:
        if not any(keyword in text for keyword in EXERCISE_KEYWORDS):
            return

        if any(marker in text for marker in ("习惯", "一般", "通常", "平时", "喜欢", "经常")):
            for preference in self._extract_time_preferences(text):
                add_memory(
                    content=f"用户习惯{preference}运动。",
                    memory_type="habit",
                    topic="exercise_time",
                    slot="exercise_time",
                    value=preference,
                    domain="exercise",
                    salience=0.88,
                    confidence=0.9,
                    tags=["exercise", "time", preference],
                )

        for activity in self._extract_exercise_activities(text):
            if any(marker in text for marker in ("项目类型", "运动项目", "锻炼项目", "一般进行", "平时进行", "喜欢", "经常", "习惯")):
                add_memory(
                    content=f"用户常进行的运动项目是{activity}。",
                    memory_type="habit",
                    topic="exercise_activity",
                    slot="exercise_activity",
                    value=activity,
                    domain="exercise",
                    salience=0.86,
                    confidence=0.88,
                    tags=["exercise", "activity", activity],
                )

        freq_match = re.search(r"每周(?:大概|大约|通常|一般)?(\d+)次", text)
        if freq_match:
            frequency = f"每周{freq_match.group(1)}次"
            add_memory(
                content=f"用户一般{frequency}运动。",
                memory_type="habit",
                topic="exercise_frequency",
                slot="exercise_frequency",
                value=frequency,
                domain="exercise",
                salience=0.8,
                confidence=0.84,
                tags=["exercise", "frequency"],
            )

    def _extract_diet_memories(self, text: str, add_memory) -> None:
        for item in re.findall(r"(?:不吃|不太吃|不喜欢吃)([\u4e00-\u9fffA-Za-z0-9]{1,10})", text):
            add_memory(
                content=f"用户饮食上不吃{item}。",
                memory_type="avoidance",
                topic="diet_avoidance",
                slot="diet_avoidance",
                value=item,
                domain="nutrition",
                salience=0.84,
                confidence=0.9,
                tags=["nutrition", "avoidance", item],
            )

        for item in re.findall(r"(?:喜欢吃|爱吃|偏好)([\u4e00-\u9fffA-Za-z0-9]{1,10})", text):
            add_memory(
                content=f"用户偏好{item}。",
                memory_type="preference",
                topic="diet_preference",
                slot="diet_preference",
                value=item,
                domain="nutrition",
                salience=0.76,
                confidence=0.82,
                tags=["nutrition", "preference", item],
            )

        for term, (canonical, confidence) in DIET_CONSTRAINT_TERMS.items():
            if term in text and "我" in text:
                add_memory(
                    content=f"用户饮食约束包含{canonical}。",
                    memory_type="constraint",
                    topic="diet_constraint",
                    slot="diet_constraint",
                    value=canonical,
                    domain="nutrition",
                    salience=0.86,
                    confidence=confidence,
                    tags=["nutrition", "constraint", canonical],
                )

        for trigger, canonical, confidence in MEAL_PATTERN_RULES:
            if trigger in text and "我" in text:
                add_memory(
                    content=f"用户的饮食模式表现为{canonical}。",
                    memory_type="habit",
                    topic="meal_pattern",
                    slot="meal_pattern",
                    value=canonical,
                    domain="nutrition",
                    salience=0.8,
                    confidence=confidence,
                    tags=["nutrition", "meal_pattern"],
                )

    def _extract_sleep_memories(self, text: str, add_memory) -> None:
        sleep_time_match = re.search(r"(?:一般|通常|平时)?(?:在)?(\d{1,2})点(?:半)?睡", text)
        if sleep_time_match and "我" in text:
            sleep_time = f"{sleep_time_match.group(1)}点睡"
            add_memory(
                content=f"用户一般{sleep_time}。",
                memory_type="habit",
                topic="sleep_time",
                slot="sleep_time",
                value=sleep_time,
                domain="sleep",
                salience=0.84,
                confidence=0.88,
                tags=["sleep", "sleep_time"],
            )

        wake_time_match = re.search(r"(?:一般|通常|平时)?(?:在)?(\d{1,2})点(?:半)?起", text)
        if wake_time_match and "我" in text:
            wake_time = f"{wake_time_match.group(1)}点起"
            add_memory(
                content=f"用户一般{wake_time}。",
                memory_type="habit",
                topic="wake_time",
                slot="wake_time",
                value=wake_time,
                domain="sleep",
                salience=0.8,
                confidence=0.86,
                tags=["sleep", "wake_time"],
            )

        for trigger, canonical, confidence in SLEEP_PATTERN_RULES:
            if trigger in text and "我" in text:
                add_memory(
                    content=f"用户的睡眠习惯表现为{canonical}。",
                    memory_type="habit",
                    topic="sleep_pattern",
                    slot="sleep_pattern",
                    value=canonical,
                    domain="sleep",
                    salience=0.82,
                    confidence=confidence,
                    tags=["sleep", "pattern"],
                )

    def _extract_lifestyle_memories(self, text: str, add_memory) -> None:
        for trigger, canonical, confidence in LIFESTYLE_CONSTRAINT_RULES:
            if trigger in text and "我" in text:
                add_memory(
                    content=f"用户的生活方式约束包括{canonical}。",
                    memory_type="constraint",
                    topic="lifestyle_constraint",
                    slot="lifestyle_constraint",
                    value=canonical,
                    domain="lifestyle",
                    salience=0.78,
                    confidence=confidence,
                    tags=["lifestyle", "constraint"],
                )

    def _extract_time_preferences(self, text: str) -> list[str]:
        preferences: list[str] = []
        for raw, canonical in DAY_PREFERENCE_ALIASES.items():
            if raw in text and canonical not in preferences:
                preferences.append(canonical)
        for preference in TIME_PREFERENCE_WORDS:
            if preference in text and preference not in preferences:
                preferences.append(preference)
        for weekday in ("周一", "周二", "周三", "周四", "周五", "周六", "周日"):
            if weekday in text and weekday not in preferences:
                preferences.append(weekday)
        return preferences

    def _extract_exercise_activities(self, text: str) -> list[str]:
        activities: list[str] = []
        for activity in EXERCISE_ACTIVITY_TYPES:
            if activity in text and activity not in activities:
                activities.append(activity)
        return activities

    def _denoise_memories(self, memories: list[dict], *, limit: int) -> list[dict]:
        """Keep only high-value memory facts by deduping and salience-aware reranking."""
        deduped: dict[str, dict] = {}
        for memory in memories:
            content = re.sub(r"\s+", " ", str(memory.get("content") or "")).strip()
            if len(content) < 4:
                continue
            metadata = memory.get("metadata") or {}
            key = "::".join(
                [
                    str(memory.get("memory_type") or metadata.get("memory_type") or ""),
                    str(memory.get("topic") or metadata.get("topic") or ""),
                    content,
                ]
            )
            score = float(memory.get("score") or 0.0)
            salience = float(metadata.get("salience") or 0.0)
            confidence = float(metadata.get("confidence") or 0.0)
            previous = deduped.get(key)
            if previous is None:
                deduped[key] = memory
                continue
            previous_score = float(previous.get("score") or 0.0)
            previous_salience = float((previous.get("metadata") or {}).get("salience") or 0.0)
            previous_confidence = float((previous.get("metadata") or {}).get("confidence") or 0.0)
            if (score, salience, confidence) > (previous_score, previous_salience, previous_confidence):
                deduped[key] = memory

        filtered = list(deduped.values())
        filtered.sort(
            key=lambda item: (
                float(item.get("score") or 0.0),
                float((item.get("metadata") or {}).get("salience") or 0.0),
                float((item.get("metadata") or {}).get("confidence") or 0.0),
            ),
            reverse=True,
        )
        return filtered[:limit]

    def _embedding_model_instance(self) -> EmbeddingModel:
        if self._embedding_model is None:
            model_cfg = EmbeddingModel.MODELS.get(settings.rag_embedding_model, EmbeddingModel.MODELS["mock"])
            is_dashscope = model_cfg.get("provider") == "dashscope"
            self._embedding_model = EmbeddingModel(
                model_name=settings.rag_embedding_model,
                api_key=settings.dashscope_api_key if is_dashscope else None,
                api_base=settings.dashscope_base_url if is_dashscope else None,
                api_model=settings.dashscope_embedding_model if is_dashscope else None,
                batch_size=settings.rag_embedding_batch_size,
                dimension=settings.dashscope_embedding_dimension if is_dashscope else None,
                request_timeout=settings.dashscope_request_timeout,
            )
        return self._embedding_model

    def _stable_memory_id(
        self,
        user_id: str,
        memory_type: str,
        topic: str,
        content: str,
    ) -> str:
        payload = f"{user_id}::{memory_type}::{topic}::{content}"
        return hashlib.sha1(payload.encode("utf-8")).hexdigest()


long_term_memory = LongTermMemory()
