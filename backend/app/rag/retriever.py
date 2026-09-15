import asyncio
import hashlib
import logging
import time
from typing import Any

from app.config import settings
from app.core.time import utc_isoformat
from app.rag.embeddings import EmbeddingModel
from app.rag.reranker import Reranker

logger = logging.getLogger(__name__)

def _is_vector_dimension_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return "different dimension" in message or "query vector has a different dimension" in message

class ElasticsearchHybridRetriever:
    """Hybrid Elasticsearch retriever using BM25 + dense-vector kNN.

    Retrieval flow:
    1. Encode query with DashScope embedding API.
    2. Run BM25 lexical search in Elasticsearch.
    3. Run dense-vector kNN search in Elasticsearch.
    4. Fuse both ranked lists with weighted RRF.
    5. Optionally rerank the fused candidates.
    """

    SOURCE_FIELDS = [
        "id",
        "title",
        "content",
        "metadata",
        "source",
        "updated_at",
    ]

    def __init__(
        self,
        es_url: str,
        index_name: str,
        embedding_model: EmbeddingModel,
        top_k: int = 5,
        candidate_k: int = 20,
        vector_weight: float = 0.65,
        bm25_weight: float = 0.35,
        reranker: Reranker | None = None,
        username: str | None = None,
        password: str | None = None,
        api_key: str | None = None,
        rrf_rank_constant: int = 60,
    ):
        self.es_url = es_url
        self.index_name = index_name
        self.embedding_model = embedding_model
        self.top_k = top_k
        self.candidate_k = candidate_k
        self.vector_weight = vector_weight
        self.bm25_weight = bm25_weight
        self.reranker = reranker
        self.username = username
        self.password = password
        self.api_key = api_key
        self.rrf_rank_constant = rrf_rank_constant
        self._client = None

    async def close(self) -> None:
        """Close the Elasticsearch client."""
        if self._client is not None:
            await self._client.close()
            self._client = None

    async def initialize(self, seed_documents: list[dict] | None = None) -> None:
        """Connect to Elasticsearch, create index, and optionally seed data."""
        await self._connect()
        await self._ensure_index()

        if settings.rag_seed_on_empty and seed_documents:
            count = await self._client.count(index=self.index_name)
            if count.get("count", 0) == 0:
                logger.info(
                    "[RAG] Index %s is empty; indexing %d seed documents",
                    self.index_name,
                    len(seed_documents),
                )
                await self.add_documents(seed_documents)

    async def _connect(self):
        """Create the async Elasticsearch client."""
        if self._client is not None:
            return self._client

        try:
            from elasticsearch import AsyncElasticsearch
        except ImportError as exc:
            raise RuntimeError(
                "Production RAG requires elasticsearch[async]. "
                "Install dependencies from requirements.txt."
            ) from exc

        kwargs: dict[str, Any] = {}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        elif self.username and self.password:
            kwargs["basic_auth"] = (self.username, self.password)

        self._client = AsyncElasticsearch(self.es_url, **kwargs)
        return self._client

    async def _ensure_index(self):
        """Create the knowledge index with BM25 text and dense vector fields."""
        exists = await self._client.indices.exists(index=self.index_name)
        if exists:
            await self._warn_if_embedding_dimension_mismatch()
            return

        mapping = {
            "mappings": {
                "properties": {
                    "id": {"type": "keyword"},
                    "title": {"type": "text"},
                    "content": {"type": "text"},
                    "source": {"type": "keyword"},
                    "metadata": {"type": "object", "dynamic": True},
                    "updated_at": {"type": "date"},
                    "embedding": {
                        "type": "dense_vector",
                        "dims": self.embedding_model.dimension,
                        "index": True,
                        "similarity": "cosine"
                    },
                }
            }
        }
        await self._client.indices.create(index=self.index_name, body=mapping)
        logger.info("[RAG] Created Elasticsearch index: %s", self.index_name)

    async def _warn_if_embedding_dimension_mismatch(self) -> None:
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
            logger.debug("[RAG] Failed to inspect index mapping for %s", self.index_name, exc_info=True)
            return

        if dims and int(dims) != self.embedding_model.dimension:
            logger.warning(
                "[RAG] Elasticsearch index %s embedding dims=%s, current model dims=%s. "
                "Vector retrieval will be skipped until the index is rebuilt; BM25 retrieval remains available.",
                self.index_name,
                dims,
                self.embedding_model.dimension,
            )

    async def add_documents(self, documents: list[dict]) -> list[str]:
        """Index documents into Elasticsearch with dense vectors."""
        if not documents:
            return []

        await self._connect()
        contents = [doc.get("content", "") for doc in documents]
        embeddings = await asyncio.to_thread(self.embedding_model.encode, contents)

        indexed_ids: list[str] = []
        for doc, embedding in zip(documents, embeddings):
            content = doc.get("content", "")
            if not content:
                continue

            doc_id = doc.get("id") or self._stable_doc_id(content)
            indexed_doc = {
                "id": doc_id,
                "title": doc.get("title", ""),
                "content": content,
                "source": doc.get("source", "seed"),
                "metadata": doc.get("metadata", {}),
                "updated_at": doc.get("updated_at") or utc_isoformat(),
                "embedding": embedding,
            }
            try:
                await self._client.index(
                    index=self.index_name,
                    id=doc_id,
                    document=indexed_doc,
                )
            except Exception as exc:
                if not _is_vector_dimension_error(exc):
                    raise
                indexed_doc.pop("embedding", None)
                logger.warning(
                    "[RAG] Skipping vector field while indexing %s because index %s has a different embedding dimension. "
                    "Document will still be searchable by BM25.",
                    doc_id,
                    self.index_name,
                )
                await self._client.index(
                    index=self.index_name,
                    id=doc_id,
                    document=indexed_doc,
                )
            indexed_ids.append(doc_id)

        if indexed_ids:
            await self._client.indices.refresh(index=self.index_name)
        return indexed_ids

    async def search(self, query: str) -> list[dict]:
        """Retrieve top-k knowledge chunks for a user query."""
        await self._connect()

        query_vector = await asyncio.to_thread(self.embedding_model.encode, query)
        query_vector = query_vector[0]

        bm25_results, vector_results = await asyncio.gather(
            self._bm25_search(query),
            self._vector_search(query_vector)
        )

        fused = self._fuse_ranked_results(
            [
                ("bm25", bm25_results, self.bm25_weight),
                ("vector", vector_results, self.vector_weight)
            ]
        )

        if self.reranker and fused:
            contents = [doc["content"] for doc in fused]
            rerank_scores = await self.reranker.rerank(query, contents, top_k=len(contents))
            for doc, rerank_score in zip(fused, rerank_scores):
                doc["rerank_score"] = rerank_score
                doc["score"] = rerank_score
            fused.sort(key=lambda item: item["score"], reverse=True)

        return fused[:self.top_k]

    async def _bm25_search(self, query: str) -> list[dict]:
        body = {
            "size": self.candidate_k,
            "_source": self.SOURCE_FIELDS,
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": [
                        "content^3",
                        "title^2",
                        "metadata.topic^2",
                        "metadata.category"
                    ]
                }
            }
        }
        response = await self._client.search(index=self.index_name, body=body)
        return [self._hit_to_doc(hit, "bm25") for hit in response["hits"]["hits"]]

    async def _vector_search(self, query_vector: list[float]) -> list[dict]:
        # body = {
        #     "size": self.candidate_k,
        #     "_source": self.SOURCE_FIELDS,
        #     "knn": {
        #         "field": "embedding",
        #         "query_vector": query_vector,
        #         "k": self.candidate_k,
        #         "num_candidates": max(self.candidate_k * 5, 100),
        #     },
        # }
        # try:
        #     response = await self._client.search(index=self.index_name, body=body)
        # except Exception as exc:
        #     if not _is_vector_dimension_error(exc):
        #         raise
        #     logger.warning(
        #         "[RAG] Vector retrieval skipped for index=%s because query vector dims=%s do not match existing index mapping. "
        #         "Delete/rebuild the index to enable DashScope vector retrieval.",
        #         self.index_name,
        #         len(query_vector),
        #     )
        #     return []
        # return [self._hit_to_doc(hit, "vector") for hit in response["hits"]["hits"]]
        body = {
            "size": self.candidate_k,
            "_source": self.SOURCE_FIELDS,
            "query": {
                "script_score": {
                    "query": {"exists": {"field": "embedding"}},
                    "script": {
                        "source": "cosineSimilarity(params.query_vector, 'embedding') + 1.0",
                        "params": {
                            "query_vector": query_vector,
                        },
                    },
                },
            },
        }
        try:
            response = await self._client.search(index=self.index_name, body=body)
        except Exception as exc:
            exc_str = str(exc).lower()
            if _is_vector_dimension_error(exc) or "script_score" in exc_str:
                logger.warning(
                    "[RAG] Vector retrieval skipped for index=%s: %s",
                    self.index_name,
                    exc,
                )
                return []
            raise
        return [self._hit_to_doc(hit, "vector") for hit in response["hits"]["hits"]]


    def _fuse_ranked_results(
        self,
        ranked_lists: list[tuple[str, list[dict], float]],
    ) -> list[dict]:
        """Fuse ranked lists with weighted reciprocal-rank fusion."""
        fused: dict[str, dict] = {}

        for retrieval_type, docs, weight in ranked_lists:
            for rank, doc in enumerate(docs, start=1):
                doc_id = doc["id"]
                rrf_score = weight / (self.rrf_rank_constant + rank)

                if doc_id not in fused:
                    fused[doc_id] = {
                        **doc,
                        "score": 0.0,
                        "retrieval": {
                            "sources": [],
                            "raw_scores": {},
                        },
                    }

                fused_doc = fused[doc_id]
                fused_doc["score"] += rrf_score
                fused_doc["retrieval"]["sources"].append(retrieval_type)
                fused_doc["retrieval"]["raw_scores"][retrieval_type] = doc.get("raw_score", 0.0)

        results = list(fused.values())
        results.sort(key=lambda item: item["score"], reverse=True)
        return results

    def _hit_to_doc(self, hit: dict, retrieval_type: str) -> dict:
        source = hit.get("_source", {})
        metadata = source.get("metadata") or {}
        return {
            "id": source.get("id") or hit.get("_id"),
            "title": source.get("title", ""),
            "content": source.get("content", ""),
            "metadata": metadata,
            "source": source.get("source", ""),
            "score": float(hit.get("_score") or 0.0),
            "raw_score": float(hit.get("_score") or 0.0),
            "retrieval": {
                "sources": [retrieval_type],
                "raw_scores": {retrieval_type: float(hit.get("_score") or 0.0)},
            },
        }

    def _stable_doc_id(self, content: str) -> str:
        return hashlib.sha256(content.encode('utf-8')).hexdigest()[:32]

class RAGRetriever:
    """Production RAG facade using Elasticsearch + DashScope embeddings."""

    def __init__(self, top_k: int | None = None):
        self.top_k = top_k or settings.rag_top_k
        self._retriever: ElasticsearchHybridRetriever | None = None
        self._initialized = False
        self._embedding_model: EmbeddingModel | None = None
        self._reranker: Reranker | None = None
        self._initialize_lock = asyncio.Lock()

    @staticmethod
    def _build_embedding_model() -> EmbeddingModel:
        model_cfg = EmbeddingModel.MODELS.get(settings.rag_embedding_model, EmbeddingModel.MODELS["mock"])
        is_dashscope = model_cfg.get("provider") == "dashscope"
        return EmbeddingModel(
            model_name=settings.rag_embedding_model,
            api_key=settings.dashscope_api_key if is_dashscope else None,
            api_base=settings.dashscope_base_url if is_dashscope else None,
            api_model=settings.dashscope_embedding_model if is_dashscope else None,
            batch_size=settings.rag_embedding_batch_size,
            dimension=settings.dashscope_embedding_dimension if is_dashscope else None,
            request_timeout=settings.dashscope_request_timeout,
        )

    @staticmethod
    def _build_reranker() -> Reranker:
        return Reranker(model_name=settings.rag_reranker_model)

    async def initialize(self):
        """Initialize the production retriever."""
        if self._initialized:
            return

        async with self._initialize_lock:
            if self._initialized:
                return

            if not settings.elasticsearch_url:
                raise RuntimeError(
                    "Production RAG requires ELASTICSEARCH_URL. "
                    "Set ELASTICSEARCH_URL and ensure Elasticsearch is running."
                )

            started_at = time.perf_counter()
            logger.info(
                "[RAG] initialize start index=%s embedding_model=%s",
                settings.rag_index_name,
                settings.rag_embedding_model,
            )

            try:
                if self._embedding_model is None:
                    self._embedding_model = await asyncio.to_thread(self._build_embedding_model)

                if settings.rag_use_reranker and self._reranker is None:
                    self._reranker = await asyncio.to_thread(self._build_reranker)

                if self._retriever is None:
                    self._retriever = ElasticsearchHybridRetriever(
                        es_url=settings.elasticsearch_url,
                        index_name=settings.rag_index_name,
                        embedding_model=self._embedding_model,
                        top_k=self.top_k,
                        candidate_k=settings.rag_candidate_k,
                        vector_weight=settings.rag_vector_weight,
                        bm25_weight=settings.rag_bm25_weight,
                        reranker=self._reranker,
                        username=settings.elasticsearch_username,
                        password=settings.elasticsearch_password,
                        api_key=settings.elasticsearch_api_key,
                    )
                await self._retriever.initialize(seed_documents=self._load_seed_knowledge())
                self._initialized = True
                logger.info(
                "[RAG] initialize finished in %.2fs",
                time.perf_counter() - started_at,
                )
            except Exception:
                logger.exception(
                    "[RAG] initialize failed after %.2fs",
                    time.perf_counter() - started_at,
                    )
                if self._retriever is not None:
                    await self._retriever.close()
                    self._retriever = None
                raise

    def _load_seed_knowledge(self) -> list[dict]:
        """Load starter health knowledge for bootstrapping a new ES index."""
        return [
            {
                "id": "k1",
                "title": "成年人饮水量建议",
                "content": "成年人每日推荐饮水量约为1500-2000毫升，约8杯水。运动量大或天气炎热时需适当增加。",
                "source": "seed_health_knowledge",
                "metadata": {"category": "nutrition", "topic": "hydration"},
            },
            {
                "id": "k2",
                "title": "成年人睡眠时间建议",
                "content": "成年人每晚推荐睡眠时间为7-9小时。长期睡眠不足会增加心血管疾病、糖尿病等慢性病风险。",
                "source": "seed_health_knowledge",
                "metadata": {"category": "lifestyle", "topic": "sleep"},
            },
            {
                "id": "k3",
                "title": "成年人有氧运动建议",
                "content": "成年人每周推荐进行至少150分钟中等强度有氧运动，或75分钟高强度运动。可分散到每周3-5天完成。",
                "source": "seed_health_knowledge",
                "metadata": {"category": "exercise", "topic": "aerobic"},
            },
            {
                "id": "k4",
                "title": "BMI 正常范围",
                "content": "BMI（身体质量指数）正常范围为18.5-23.9。低于18.5为偏瘦，24-27.9为超重，28及以上为肥胖。",
                "source": "seed_health_knowledge",
                "metadata": {"category": "health", "topic": "BMI"},
            },
            {
                "id": "k5",
                "title": "高血压判定标准",
                "content": "高血压定义为收缩压≥140mmHg和/或舒张压≥90mmHg。正常血压为收缩压<120mmHg且舒张压<80mmHg。",
                "source": "seed_health_knowledge",
                "metadata": {"category": "health", "topic": "blood_pressure"},
            },
            {
                "id": "k6",
                "title": "空腹血糖参考范围",
                "content": "正常空腹血糖值为3.9-6.1mmol/L。空腹血糖≥7.0mmol/L或餐后2小时血糖≥11.1mmol/L可考虑糖尿病诊断。",
                "source": "seed_health_knowledge",
                "metadata": {"category": "health", "topic": "blood_sugar"},
            },
            {
                "id": "k7",
                "title": "膳食纤维摄入建议",
                "content": "膳食纤维每日推荐摄入量为25-30克。富含纤维的食物包括全谷物、豆类、蔬菜、水果等。",
                "source": "seed_health_knowledge",
                "metadata": {"category": "nutrition", "topic": "fiber"},
            },
            {
                "id": "k8",
                "title": "蛋白质摄入建议",
                "content": "成年人每日蛋白质推荐摄入量为每公斤体重0.8-1.2克。运动人群可适当增加至1.2-2.0克/公斤体重。",
                "source": "seed_health_knowledge",
                "metadata": {"category": "nutrition", "topic": "protein"},
            },
        ]

    async def add_documents(self, documents: list[dict]) -> list[str]:
        """Add knowledge documents to the production RAG index."""
        if not self._initialized:
            await self.initialize()
        return await self._retriever.add_documents(documents)

    async def retrieve(self, query: str) -> list[dict]:
        """Search knowledge base. Returns {id, content, metadata, score} docs."""
        if not self._initialized:
            await self.initialize()
        return await self._retriever.search(query)

    async def close(self):
        """Close internal async clients."""
        if self._retriever is not None:
            await self._retriever.close()
        self._retriever = None
        self._initialized = False

rag_retriever = RAGRetriever()