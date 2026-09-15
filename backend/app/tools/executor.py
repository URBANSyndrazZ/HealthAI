import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from app.tools.registry import tool_registry

logger = logging.getLogger(__name__)

DEFAULT_TOOL_WHITELIST: dict[str, set[str]] = {
    "health_advisor": {"search_knowledge_base", "search_memory", "get_user_profile", "get_health_records"},
    "nutrition": {"query_nutrition"},
    "environment": {"resolve_location", "fetch_air_quality", "fetch_weather"},
    "exercise": {"generate_exercise_plan", "get_environment_data"},
}

@dataclass
class ToolExecutionContext:
    """Metadata used by the executor for policy and observability."""

    agent_name: str = ""
    trace_id: str = ""
    user_id: str = ""
    session_id: str = ""
    timeout_seconds: float | None = None
    retry: int = 0
    required: bool = False
    allow_fallback: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)

@dataclass
class ToolResult:
    tool_name: str
    status: str            # success / failed / timeout / skipped
    data: Any = None
    error: dict | None = None
    latency_ms: int = 0
    source: str = "tool"
    trace_id: str = ""
    retry_count: int = 0

    def model_dump(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status,
            "data": self.data,
            "error": self.error,
            "latency_ms": self.latency_ms,
            "source": self.source,
            "trace_id": self.trace_id,
            "retry_count": self.retry_count,
        }

class ToolExecutor:
    """Central execution point for all registered tools."""

    def __init__(self, whitelist: dict[str, set[str]] | None = None):
        self.whitelist = whitelist or DEFAULT_TOOL_WHITELIST

    def _is_allowed(self, tool_name: str, context: ToolExecutionContext) -> bool:
        if not context.agent_name:
            return True
        allowed = self.whitelist.get(context.agent_name)
        return allowed is None or tool_name in allowed

    def _trace(self, result: ToolResult) -> dict[str, Any]:
        return result.model_dump()

    def _failure(
        self,
        tool_name: str,
        context: ToolExecutionContext,
        started_at: float,
        status: str,
        message: str,
        *,
        retry_count: int = 0,
        exc: Exception | None = None,
    ) -> ToolResult:
        error = {"message": message}
        if exc is not None:
            error["type"] = exc.__class__.__name__
        result = ToolResult(
            tool_name=tool_name,
            status=status,
            data=None,
            error=error,
            latency_ms=round((time.time() - started_at) * 1000),
            source="executor",
            trace_id=context.trace_id,
            retry_count=retry_count,
        )
        logger.warning(
            "[tool_executor] %s status=%s latency=%sms error=%s trace=%s",
            tool_name,
            status,
            result.latency_ms,
            message,
            context.trace_id,
        )
        return result

    def execute_sync(
        self,
        tool_name: str,
        *,
        context: ToolExecutionContext|None=None,
        **kwargs: Any
    ) -> ToolResult:
        """Execute a synchronous registered tool."""
        context = context or ToolExecutionContext()
        started_at = time.perf_counter()

        if not self._is_allowed(tool_name, context):
            return self._failure(
                tool_name,
                context,
                started_at,
                "skipped",
                f"Tool {tool_name} is not allowed for agent {context.agent_name}"
            )

        tool = tool_registry.get(tool_name)
        if tool is None:
            return self._failure(tool_name, context, started_at, "failed", "Tool is not registered")

        attempts = max(context.retry, 0) + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                data = tool.invoke_sync(**kwargs)
                source = "tool"
                if isinstance(data, dict):
                    source = str(data.get("data_scource") or data.get("source") or source)
                result = ToolResult(
                    tool_name=tool_name,
                    status="success",
                    data=data,
                    latency_ms=round((time.time() - started_at) * 1000),
                    source=source,
                    trace_id=context.trace_id,
                    retry_count=attempt - 1,
                )
                logger.info(
                    "[tool_executor] %s status=success latency=%sms retry=%d source=%s trace=%s",
                    tool_name,
                    result.latency_ms,
                    result.retry_count,
                    result.source,
                    context.trace_id,
                )
                return result
            except Exception as exc:
                last_error = exc
                logger.exception("[tool_executor] %s attempt %d/%d failed", tool_name, attempt, attempts)

        return self._failure(
            tool_name,
            context,
            started_at,
            "failed",
            str(last_error) if last_error else "Unknown tool error",
            retry_count=max(attempts - 1, 0),
            exc=last_error,
        )

    async def execute(
        self,
        tool_name: str,
        *,
        context: ToolExecutionContext|None=None,
        **kwargs: Any
    ) -> ToolResult:
        """Execute a registered tool, supporting both async and sync functions."""
        context = context or ToolExecutionContext()
        started_at = time.perf_counter()

        if not self._is_allowed(tool_name, context):
            return self._failure(
                tool_name,
                context,
                started_at,
                "skipped",
                f"Tool {tool_name} is not allowed for agent {context.agent_name}",
            )

        tool = tool_registry.get(tool_name)
        if tool is None:
            return self._failure(tool_name, context, started_at, "failed", "Tool is not registered")

        attempts = max(context.retry, 0) + 1
        timeout = context.timeout_seconds
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                coro = tool.invoke(**kwargs)
                data = await asyncio.wait_for(coro, timeout=timeout) if timeout else await coro
                source = "tool"
                if isinstance(data, dict):
                    source = str(data.get("data_source") or data.get("source") or source)
                return ToolResult(
                    tool_name=tool_name,
                    status="success",
                    data=data,
                    latency_ms=round((time.time() - started_at) * 1000),
                    source=source,
                    trace_id=context.trace_id,
                    retry_count=attempt - 1,
                )
            except asyncio.TimeoutError:
                return self._failure(
                    tool_name,
                    context,
                    started_at,
                    "timeout",
                    f"Timeout after {timeout}s",
                    retry_count=attempt - 1,
                )
            except Exception as exc:
                last_error = exc
                logger.exception("[tool_executor] %s attempt %d/%d failed", tool_name, attempt, attempts)

        return self._failure(
            tool_name,
            context,
            started_at,
            "failed",
            str(last_error) if last_error else "Unknown tool error",
            retry_count=max(attempts - 1, 0),
            exc=last_error,
        )

tool_executor = ToolExecutor()

def append_tool_trace(state: dict[str, Any], result: ToolResult) -> None:
    """Append a compact tool trace to an agent state dict."""
    state.setdefault("tool_trace", []).append(result.model_dump())