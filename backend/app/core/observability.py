"""Request tracing and structured logging utilities"""
import json
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware

TRACE_ID_HEADER = "X-Trace-ID"
_trace_id: ContextVar[str] = ContextVar("trace_id", default="")

def get_trace_id() -> str:
    """Return the trace id bound to the current request context"""
    return _trace_id.get()

def set_trace_id(trace_id: str) -> None:
    """Bind a trace id to the current request context"""
    _trace_id.set(trace_id)

class JsonLogFormatter(logging.Formatter):
    """Format logs as compact JSON with trace metadata."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None) or get_trace_id() or None,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)

def configure_loggin(level: int = logging.INFO) -> None:
    """Configure root logging once for the API process"""
    root = logging.getLogger()
    root.setLevel(level)

    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    root.handlers = [handler]

class RequestTraceMiddleware(BaseHTTPMiddleware):
    """Attach a trace id to every request and response"""
    async def dispatch(self, request, call_next):
        trace_id = request.headers.get(TRACE_ID_HEADER) or str(uuid.uuid4())
        set_trace_id(trace_id)
        request.state.trace_id = trace_id

        started_at = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
            logging.getLogger("app.request").exception(
                "request failed mathod=%s path=%s elapsed_ms=%s",
                request.method, request.url.path, elapsed_ms
            )
            raise

        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 2)
        response.headers[TRACE_ID_HEADER] = trace_id
        logging.getLogger("app.request").info(
            "request completed method=%s path=%s status=%s elapsed_ms=%s",
            request.method, request.url.path, response.status_code, elapsed_ms
        )
        return response