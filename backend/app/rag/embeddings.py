"""Embedding model for vectorizing text."""

import json
import logging
import urllib.error
import urllib.request
from typing import Any, List, Optional, Union

logger = logging.getLogger(__name__)

DASHSCOPE_COMPATIBLE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class EmbeddingModel:
    """Embedding model for text vectorization.

    This class provides an interface for generating text embeddings. Production
    defaults to DashScope's OpenAI-compatible embedding API; local BGE models
    are kept as an offline fallback, and mock embeddings are used in tests.

    Attributes:
        model_name: Name of the embedding model
        dimension: Embedding vector dimension
        batch_size: Batch size for embedding generation
    """

    # Model configurations
    MODELS = {
        "dashscope-text-embedding-v4": {
            "provider": "dashscope",
            "api_model": "text-embedding-v4",
            "dimension": 1024,
            "max_length": 8192,
            "max_batch_size": 10,
        },
        "text-embedding-v4": {
            "provider": "dashscope",
            "api_model": "text-embedding-v4",
            "dimension": 1024,
            "max_length": 8192,
            "max_batch_size": 10,
        },
        "dashscope-text-embedding-v3": {
            "provider": "dashscope",
            "api_model": "text-embedding-v3",
            "dimension": 1024,
            "max_length": 8192,
            "max_batch_size": 10,
        },
        "bge-m3": {"dimension": 1024, "max_length": 8192},
        "bge-large-zh": {"dimension": 1024, "max_length": 512},
        "bge-base-zh": {"dimension": 768, "max_length": 512},
        "e5-large": {"dimension": 1024, "max_length": 512},
        "mock": {"dimension": 768, "max_length": 512},
    }

    def __init__(
        self,
        model_name: str = "mock",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        api_model: Optional[str] = None,
        batch_size: int = 32,
        device: Optional[str] = None,
        dimension: Optional[int] = None,
        request_timeout: int = 60,
    ):
        """Initialize the embedding model.

        Args:
            model_name: Name of the model to use
            api_key: API key for external embedding services
            api_base: Base URL for API
            api_model: Provider-side model name for external embedding services
            batch_size: Batch size for embedding generation
        """
        self.model_name = model_name
        self.api_key = api_key
        self.batch_size = batch_size
        self.device = device
        self.request_timeout = request_timeout

        # Get model config
        config = self.MODELS.get(model_name, self.MODELS["mock"])
        self.provider = config.get("provider", "local")
        self.api_model = api_model or config.get("api_model", model_name)
        self.api_base = (api_base or config.get("api_base") or DASHSCOPE_COMPATIBLE_BASE_URL).rstrip("/")
        self.dimension = dimension or config["dimension"]
        self.max_length = config["max_length"]
        self.max_batch_size = int(config.get("max_batch_size") or self.batch_size)

        # Initialize model (in production, load actual model)
        self._model = None
        self._initialize_model()

        logger.info(f"Initialized EmbeddingModel: {model_name} (dim={self.dimension})")

    def _initialize_model(self):
        """Initialize the embedding model."""
        if self.model_name == "mock":
            # Mock model - no initialization needed
            return

        if self.provider == "dashscope":
            # DashScope is called lazily over HTTP in encode().
            return

        if self.model_name == "bge-m3":
            try:
                from FlagEmbedding import BGEM3FlagModel

                self._model = BGEM3FlagModel("BAAI/bge-m3", use_fp16=False)
                logger.info("Loaded BGE-M3 embedding model")
                return
            except ImportError as exc:
                raise RuntimeError(
                    "BGE-M3 requires FlagEmbedding. Install requirements-ml.txt "
                    "before starting the production RAG service."
                ) from exc

        if self.model_name.startswith("bge"):
            try:
                from FlagEmbedding import FlagModel

                model_path = self.model_name if "/" in self.model_name else f"BAAI/{self.model_name}"
                self._model = FlagModel(
                    model_path,
                    query_instruction_for_retrieval="为这个句子生成表示以用于检索相关文章：",
                    use_fp16=False,
                )
                logger.info("Loaded embedding model: %s", model_path)
                return
            except ImportError as exc:
                raise RuntimeError(
                    f"{self.model_name} requires FlagEmbedding. Install requirements-ml.txt "
                    "before starting the production RAG service."
                ) from exc

        raise ValueError(f"Unsupported embedding model: {self.model_name}")

    def encode(
        self,
        texts: Union[str, List[str]],
        normalize: bool = True,
        show_progress: bool = False,
    ) -> List[List[float]]:
        """Encode texts to embedding vectors.

        Args:
            texts: Single text or list of texts to encode
            normalize: Whether to normalize vectors
            show_progress: Whether to show progress bar

        Returns:
            List of embedding vectors
        """
        # Handle single text input
        if isinstance(texts, str):
            texts = [texts]

        # Truncate texts to max length
        texts = [t[: self.max_length] for t in texts]

        # Generate embeddings
        if self.model_name == "mock":
            embeddings = self._mock_encode(texts)
        elif self.provider == "dashscope":
            embeddings = self._dashscope_encode(texts)
        else:
            # In production, use actual model
            embeddings = self._model_encode(texts, show_progress)

        # Normalize if requested
        if normalize:
            embeddings = self._normalize(embeddings)

        return embeddings

    def _mock_encode(self, texts: List[str]) -> List[List[float]]:
        """Generate mock embeddings for testing."""
        import hashlib
        import random

        embeddings = []
        for text in texts:
            # Use hash to generate consistent but unique vectors
            hash_obj = hashlib.md5(text.encode())
            hash_int = int(hash_obj.hexdigest(), 16)

            # Generate pseudo-random vector based on hash
            random.seed(hash_int)
            vector = [random.uniform(-1, 1) for _ in range(self.dimension)]

            # Normalize
            magnitude = sum(x**2 for x in vector) ** 0.5
            if magnitude > 0:
                vector = [x / magnitude for x in vector]

            embeddings.append(vector)

        return embeddings

    def _dashscope_encode(self, texts: List[str]) -> List[List[float]]:
        """Encode texts with DashScope's OpenAI-compatible embedding API."""
        if not self.api_key:
            raise RuntimeError(
                "DashScope embedding API requires DASHSCOPE_API_KEY. "
                "Set DASHSCOPE_API_KEY or use RAG_EMBEDDING_MODEL=mock for tests."
            )

        embeddings: list[list[float]] = []
        batch_size = max(1, min(self.batch_size, self.max_batch_size))
        for start in range(0, len(texts), batch_size):
            batch = texts[start : start + batch_size]
            payload = {
                "model": self.api_model,
                "input": batch,
                "encoding_format": "float",
                "dimensions": self.dimension,
            }
            response = self._post_json(f"{self.api_base}/embeddings", payload)
            embeddings.extend(self._parse_embedding_response(response, expected_count=len(batch)))

        return embeddings

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"DashScope embedding API failed with HTTP {exc.code}: {error_body[:500]}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"DashScope embedding API request failed: {exc}") from exc

        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"DashScope embedding API returned invalid JSON: {body[:500]}") from exc

    def _parse_embedding_response(
        self,
        response: dict[str, Any],
        *,
        expected_count: int,
    ) -> List[List[float]]:
        """Parse OpenAI-compatible or native DashScope embedding response."""
        if isinstance(response.get("data"), list):
            items = sorted(response["data"], key=lambda item: int(item.get("index", 0)))
            vectors = [item.get("embedding") for item in items]
        else:
            native_items = (response.get("output") or {}).get("embeddings")
            if not isinstance(native_items, list):
                raise RuntimeError(f"DashScope embedding API returned no embeddings: {response}")
            items = sorted(native_items, key=lambda item: int(item.get("text_index", 0)))
            vectors = [item.get("embedding") for item in items]

        if len(vectors) != expected_count:
            raise RuntimeError(
                f"DashScope embedding API returned {len(vectors)} vectors, expected {expected_count}"
            )

        parsed: list[list[float]] = []
        for vector in vectors:
            if not isinstance(vector, list):
                raise RuntimeError("DashScope embedding API returned a malformed vector")
            parsed.append([float(value) for value in vector])
        return parsed

    def _model_encode(
        self, texts: List[str], show_progress: bool = False
    ) -> List[List[float]]:
        """Encode using an actual embedding model."""
        if self._model is None:
            raise RuntimeError(f"Embedding model {self.model_name} is not initialized")

        if self.model_name == "bge-m3":
            output = self._model.encode(
                texts,
                batch_size=self.batch_size,
                max_length=self.max_length,
                return_dense=True,
                return_sparse=False,
                return_colbert_vecs=False,
            )
            dense_vectors = output["dense_vecs"] if isinstance(output, dict) else output
            return [list(map(float, vector)) for vector in dense_vectors]

        output = self._model.encode(
            texts,
            batch_size=self.batch_size,
            max_length=self.max_length,
        )
        return [list(map(float, vector)) for vector in output]

    def _normalize(self, embeddings: List[List[float]]) -> List[List[float]]:
        """Normalize embedding vectors to unit length."""
        normalized = []
        for vector in embeddings:
            magnitude = sum(x**2 for x in vector) ** 0.5
            if magnitude > 0:
                normalized.append([x / magnitude for x in vector])
            else:
                normalized.append(vector)
        return normalized

    def similarity(self, embedding1: List[float], embedding2: List[float]) -> float:
        """Calculate cosine similarity between two embeddings.

        Args:
            embedding1: First embedding vector
            embedding2: Second embedding vector

        Returns:
            Cosine similarity score (0-1)
        """
        if len(embedding1) != len(embedding2):
            raise ValueError("Embeddings must have same dimension")

        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
        magnitude1 = sum(x**2 for x in embedding1) ** 0.5
        magnitude2 = sum(x**2 for x in embedding2) ** 0.5

        if magnitude1 == 0 or magnitude2 == 0:
            return 0.0

        return dot_product / (magnitude1 * magnitude2)
