"""
LLM Token usage tracking helpers.

The tracker is intentionally lightweight and context-local. Evaluation code can
open a tracking context around one case, while normal application request keep
running without any extra report object.
"""
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Iterator

_current_tracker: ContextVar["LLMUsageTracker | None"] = ContextVar(
    "current_llm_usage_tracker",
    default=None
)

@dataclass
class LLMUsageRecord:
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    estimated: bool
    latency_ms: float | None = None
    prompt_chars: int = 0
    completion_chars: int = 0
    stage: str = "llm.chat"

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "model": self.model,
            "stage": self.stage,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "estimated": self.estimated,
            "latency_ms": round(self.latency_ms, 2) if self.latency_ms is not None else None,
            "prompt_chars": self.prompt_chars,
            "completion_chars": self.completion_chars,
        }

class LLMUsageTracker:
    def __init__(self):
        self.records: list[LLMUsageRecord] = []
        self.started_at = time.perf_counter()

    def record(self, record: LLMUsageRecord):
        self.records.append(record)

    def summary(self, *, include_calls: bool = True) -> dict[str, Any]:
        return summarize_usage_records(self.records, include_calls=include_calls)

def get_current_usage_tracker() -> LLMUsageTracker | None:
    return _current_tracker.get()

@contextmanager
def track_llm_usage() -> Iterator[LLMUsageTracker]:
    tracker = LLMUsageTracker()
    token = _current_tracker.set(tracker)
    try:
        yield tracker
    finally:
        _current_tracker.reset(token)

def _int_value(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None

def _tokens_from_usage_metadata(response: Any) -> tuple[int | None, int | None, int | None]:
    usage = getattr(response, "usage_metadata", None)
    if not isinstance(usage, dict):
        return None, None, None
    prompt_tokens = _int_value(usage.get("input_tokens") or usage.get("prompt_tokens"))
    completion_tokens = _int_value(usage.get("output_tokens") or usage.get("completion_tokens"))
    total_tokens = _int_value(usage.get("total_tokens"))
    return prompt_tokens, completion_tokens, total_tokens

def _tokens_from_response_metadata(response: Any) -> tuple[int | None, int | None, int | None]:
    metadata = getattr(response, "response_metadata", None)
    if not isinstance(metadata, dict):
        return None, None, None
    usage = metadata.get("token_usage") or metadata.get("usage")
    if not isinstance(usage, dict):
        return None, None, None
    prompt_tokens = _int_value(usage.get("prompt_tokens") or usage.get("input_tokens"))
    completion_tokens = _int_value(usage.get("completion_tokens") or usage.get("output_tokens"))
    total_tokens = _int_value(usage.get("total_tokens"))
    return prompt_tokens, completion_tokens, total_tokens

def build_usage_record(
    *,
    response: Any,
    provider: str,
    model: str,
    prompt_chars: int,
    completion_chars: int,
    latency_ms: float | None = None,
    stage: str = "llm.chat",
) -> LLMUsageRecord:
    """
    Build a normalized usage record from LangChain response metadata.

    DeepSeek-compatible OpenAI responses usually expose either
    ``usage_metadata`` or ``response_metadata.token_usage``. Some mocked tests
    and providers do not include usage; in that case we use a conservative
    character-based estimate and mark the record as estimated.
    """
    prompt_tokens, completion_tokens, total_tokens = _tokens_from_usage_metadata(response)
    if prompt_tokens is None and completion_tokens is None and total_tokens is None:
        prompt_tokens, completion_tokens, total_tokens = _tokens_from_response_metadata(response)

    estimated = False
    if prompt_tokens is None and completion_tokens is None and total_tokens is None:
        estimated = True
        prompt_tokens = max(1, round(prompt_chars / 4) if prompt_chars else 0)
        completion_tokens = max(1, round(completion_chars / 4) if completion_chars else 0)
        total_tokens = prompt_tokens + completion_tokens
    else:
        prompt_tokens = prompt_tokens or 0
        completion_tokens = completion_tokens or 0
        total_tokens = total_tokens or (prompt_tokens + completion_tokens)

    return LLMUsageRecord(
        provider=provider,
        model=model,
        stage=stage,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        estimated=estimated,
        latency_ms=latency_ms,
        prompt_chars=prompt_chars,
        completion_chars=completion_chars,
    )

def record_llm_usage(record: LLMUsageRecord):
    tracker = get_current_usage_tracker()
    if tracker is not None:
        tracker.record(record)

def summarize_usage_records(records: list[LLMUsageRecord], *, include_calls: bool = True) -> dict[str, Any]:
    call_count = len(records)
    prompt_tokens = sum(record.prompt_tokens for record in records)
    completion_tokens = sum(record.completion_tokens for record in records)
    total_tokens = sum(record.total_tokens for record in records)
    estimated_call_count = sum(1 for record in records if record.estimated)
    actual_call_count = call_count - estimated_call_count
    lantency_values = [record.latency_ms for record in records if record.latency_ms is not None]
    summary: dict[str, Any] = {
        "call_count": call_count,
        "actual_call_count": actual_call_count,
        "estimated_call_count": estimated_call_count,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated": estimated_call_count > 0,
        "lantency_ms": round(sum(lantency_values), 2) if lantency_values else 0.0
    }
    if include_calls:
        summary["calls"] = [record.to_dict() for record in records]
    return summary

def aggregate_usage_summaries(
    summaries: list[dict[str, Any] | None],
    *,
    include_cases: bool = False,
) -> dict[str, Any]:
    valid_summaries = [summary for summary in summaries if summary]
    aggregate = {
        "call_count": sum(int(summary.get("call_count", 0)) for summary in valid_summaries),
        "actual_call_count": sum(int(summary.get("actual_call_count", 0)) for summary in valid_summaries),
        "estimated_call_count": sum(int(summary.get("estimated_call_count", 0)) for summary in valid_summaries),
        "prompt_tokens": sum(int(summary.get("prompt_tokens", 0)) for summary in valid_summaries),
        "completion_tokens": sum(int(summary.get("completion_tokens", 0)) for summary in valid_summaries),
        "total_tokens": sum(int(summary.get("total_tokens", 0)) for summary in valid_summaries),
        "estimated": any(bool(summary.get("estimated")) for summary in valid_summaries),
        "latency_ms": round(sum(float(summary.get("latency_ms", 0.0)) for summary in valid_summaries), 2)
    }
    if include_cases:
        aggregate["cases"] = valid_summaries
    return aggregate