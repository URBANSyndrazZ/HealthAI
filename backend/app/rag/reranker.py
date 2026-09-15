import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class Reranker:
    """Reranker for improving retrieval relevance.

    This reranker uses cross-encoders or similar models to
    score the relevance of documents to a query, providing
    better ranking than initial retrieval methods.

    Attributes:
        model_name: Name of the reranking model
        max_length: Maximum sequence length
        batch_size: Batch size for reranking
    """

    # Supported models
    MODELS = {
        "bge-reranker-large": {
            "dimension": 1024,
            "max_length": 512,
            "description": "BGE Reranker Large",
        },
        "bge-reranker-base": {
            "dimension": 768,
            "max_length": 512,
            "description": "BGE Reranker Base",
        },
        "cohere-rerank": {
            "dimension": None,  # API-based
            "max_length": 4096,
            "description": "Cohere Rerank API",
        },
        "mock": {
            "dimension": 768,
            "max_length": 512,
            "description": "Mock reranker for testing",
        },
    }

    def __init__(
        self,
        model_name: str = "mock",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        batch_size: int = 32,
        device: Optional[str] = None,
    ):
        """Initialize the reranker.

        Args:
            model_name: Name of the reranking model
            api_key: API key for external services
            api_base: Base URL for API
            batch_size: Batch size for reranking
            device: Device to use (cpu/cuda)
        """
        self.model_name = model_name
        self.api_key = api_key
        self.api_base = api_base
        self.batch_size = batch_size
        self.device = device or "cpu"

        # Get model config
        config = self.MODELS.get(model_name, self.MODELS["mock"])
        self.max_length = config["max_length"]

        # Initialize model
        self._model = None
        self._tokenizer = None
        self._initialize_model()

        logger.info(f"Initialized Reranker: {model_name}")

    def _initialize_model(self):
        """Initialize the reranking model."""
        if self.model_name == "mock":
            # Mock model - no initialization needed
            return

        if self.model_name.startswith("bge-reranker"):
            try:
                from FlagEmbedding import FlagReranker

                model_path = self.model_name if "/" in self.model_name else f"BAAI/{self.model_name}"
                self._model = FlagReranker(model_path, use_fp16=False)
                logger.info("Loaded reranker model: %s", model_path)
                return
            except ImportError as exc:
                raise RuntimeError(
                    f"{self.model_name} requires FlagEmbedding. Disable RAG_USE_RERANKER "
                    "or install requirements.txt."
                ) from exc

        raise ValueError(f"Unsupported reranker model: {self.model_name}")

    async def rerank(
        self,
        query: str,
        documents: List[str],
        top_k: Optional[int] = None,
    ) -> list[float]:
        """Rerank documents based on relevance to query.

        Args:
            query: Search query
            documents: List of documents to rerank
            top_k: Number of top documents to return

        Returns:
            List of relevance scores (0-1)
        """
        if not documents:
            return []

        k = top_k or len(documents)
        logger.info(f"[rerank] Reranking {len(documents)} documents")

        try:
            if self.model_name == "mock":
                scores = self._mock_rerank(query, documents)
            else:
                scores = self._model_rerank(query, documents)

            # Return scores
            return scores[:k]

        except Exception as e:
            logger.error(f"[rerank] Reranking failed: {e}")
            # Return uniform scores as fallback
            return [0.5] * min(k, len(documents))

    def _mock_rerank(self, query: str, documents: List[str]) -> List[float]:
        """Mock reranking for testing.

        Uses simple keyword matching to simulate relevance.
        """
        import re

        query_terms = set(re.findall(r"\w+", query.lower()))
        scores = []

        for doc in documents:
            doc_terms = set(re.findall(r"\w+", doc.lower()))

            # Calculate Jaccard similarity
            intersection = len(query_terms & doc_terms)
            union = len(query_terms | doc_terms)

            if union > 0:
                score = intersection / union
            else:
                score = 0.0

            # Add some randomness
            import random
            score = min(1.0, max(0.0, score + random.uniform(-0.1, 0.1)))

            scores.append(score)

        return scores

    async def _model_rerank(
        self, query: str, documents: List[str]
    ) -> List[float]:
        """Rerank using an actual cross-encoder style model."""
        if self._model is None:
            raise RuntimeError(f"Reranker model {self.model_name} is not initialized")

        pairs = [[query, doc] for doc in documents]
        scores = await asyncio.to_thread(
            self._model.compute_score,
            pairs,
            batch_size=self.batch_size,
            normalize=True,
        )
        if isinstance(scores, float):
            scores = [scores]
        return [float(score) for score in scores]