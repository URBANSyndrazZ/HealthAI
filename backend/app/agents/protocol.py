"""Shared protocol models for in-process agent coordination."""

from typing import Any, Literal

from pydantic import BaseModel, Field


AgentStatus = Literal["success", "partial", "failed", "timeout", "skipped"]


class AgentRequest(BaseModel):
    """Standard request envelope passed from orchestrator to an agent."""

    trace_id: str = ""
    user_id: str = "anonymous"
    session_id: str = ""
    agent_name: str
    task_type: str = "default"
    user_message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    user_profile: dict[str, Any] = Field(default_factory=dict)
    chat_history: list[dict[str, Any]] = Field(default_factory=list)
    relevant_memories: list[dict[str, Any]] = Field(default_factory=list)
    prior_results: dict[str, Any] = Field(default_factory=dict)
    deadline_ms: int = 30000
    locale: str = "zh-CN"


class AgentResponse(BaseModel):
    """Standard response envelope returned by every agent."""

    trace_id: str = ""
    agent_name: str
    task_type: str = "default"
    status: AgentStatus = "success"
    result: dict[str, Any] = Field(default_factory=dict)
    summary: str = ""
    confidence: float | None = None
    citations: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    suggested_questions: list[str] = Field(default_factory=list)
    error: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTask(BaseModel):
    """A task nodes in the orchestrator DAG."""

    task_id: str
    agent_name: str
    task_type: str = "default"
    payload: dict[str, Any] = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    required: bool = False
    timeout_seconds: int | None = None
    retry: int = 0