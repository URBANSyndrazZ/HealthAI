"""Http guard middleware for request limits and abuse protection"""
import hashlib
import http
import time
from collections import deque, defaultdict

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

from app.config import settings

class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose declared body size exceed the configured limit"""
    UPLOAD_PATH_PREFIXES = (
        "/api/v1/knowledge/import-file",
        "/api/v1/knowledge/import-pdf"
    )

    def __init__(self, app, max_bytes: int | None = None, upload_max_bytes: int | None = None):
        super().__init__(app)
        self.max_bytes = max_bytes
        self.upload_max_bytes = upload_max_bytes

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        max_bytes = self._max_bytes_for_path(request.url.path)
        content_length = request.headers.get("Content-Length")
        if max_bytes > 0 and content_length:
            try:
                declared_size = int(content_length)
            except ValueError:
                declared_size = 0
            if declared_size > max_bytes:
                return JSONResponse(
                    status_code=http.HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                    content={
                        "detail": "Request body too large",
                        "max_bytes": max_bytes
                    }
                )
        return await call_next(request)

    def _max_bytes_for_path(self, path: str) -> int:
        if any(path.startswith(prefix) for prefix in self.UPLOAD_PATH_PREFIXES):
            return self.upload_max_bytes if self.upload_max_bytes is not None else settings.max_upload_body_bytes
        return self.max_bytes if self.max_bytes is not None else settings.max_request_body_bytes

class InMemoryRateLimitMiddleware(BaseHTTPMiddleware):
    """Simple pre-process sliding-window rate limiter"""
    def __init__(
        self,
        app,
        *,
        general_limit: int | None = None,
        general_window_seconds: int | None = None,
        llm_limit: int | None = None,
        llm_window_seconds: int | None = None,
        enabled: bool | None = None
    ):
        super().__init__(app)
        self.general_limit = general_limit
        self.general_window_seconds = general_window_seconds
        self.llm_limit = llm_limit
        self.llm_window_seconds = llm_window_seconds
        self.enabled = enabled
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.method == "OPTIONS" or not self._enabled():
            return await call_next(request)

        limit, window_seconds = self._policy_for_path(request.url.path)
        if limit <= 0:
            return await call_next(request)

        key = self._client_key(request, limit, window_seconds)
        now = time.monotonic()
        hits = self._hits[key]
        while hits and now - hits[0] >= window_seconds:
            hits.popleft()

        if len(hits) >= limit:
            retry_after = max(1, int(window_seconds - (now - hits[0])))
            return JSONResponse(
                status_code=http.HTTPStatus.TOO_MANY_REQUESTS,
                headers={"Retry-After": str(retry_after)},
                content={
                    "detail": "Too many requests",
                    "retry_after_seconds": retry_after
                }
            )

        hits.append(now)
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(max(0, limit - len(hits)))
        return response

    def _enabled(self) -> bool:
        return self.enabled if self.enabled is not None else settings.rate_limit_enabled

    def _policy_for_path(self, path) -> tuple[int, int]:
        if path.startswith("/api/v1/chat") or path.startswith("/api/chat") or path.startswith("/api/v1/agents"):
            limit = self.llm_limit if self.llm_limit is not None else settings.rate_limit_llm
            minutes = settings.rate_limit_llm_window_minutes
            window = self.llm_window_seconds if self.llm_window_seconds is not None else minutes * 60
            return limit, window

        limit = self.general_limit if self.general_limit is not None else settings.rate_limit_general
        minutes = settings.rate_limit_window_minutes
        window = self.general_window_seconds if self.general_window_seconds is not None else minutes * 60
        return limit, window

    def _client_key(self, request: Request, limit: int, window_seconds: int) -> str:
        client_host = request.client.host if request.client else "unknown"
        auth = request.headers.get("Authorization", "")
        auth_hash = hashlib.sha256(auth.encode("utf-8")).hexdigest()[:12] if auth else "anonymous"
        return f"{client_host}:{auth_hash}:{request.url.path}:{limit}:{window_seconds}"
