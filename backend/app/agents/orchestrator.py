"""Agent Orchestrator for coordinating multi-agent workflows."""

import asyncio
import logging
import uuid
from typing import Any

from app.agents.protocol import AgentRequest, AgentResponse, AgentTask
from app.agents.registry import agent_registry

logger = logging.getLogger(__name__)


class AgentOrchestrator:
    """DAG-based orchestrator for multi-agent coordination."""

    def __init__(self, timeout_seconds: int = 30, max_retries: int = 1):
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries

    async def dispatch(
        self,
        tasks: list[dict | AgentTask],
        user_profile: dict,
        prior_results: dict | None = None,
        user_id: str = "anonymous",
        session_id: str = "",
        user_message: str = "",
        trace_id: str | None = None,
    ) -> dict[str, Any]:
        """Dispatch tasks to agents by dependency batches.

        The return shape preserves the older `completed`/`failed` keys while
        adding full protocol responses under `responses`.
        """
        trace_id = trace_id or str(uuid.uuid4())
        normalized_tasks = [self._normalize_task(task) for task in tasks]
        logger.info("Dispatching %d agent tasks (trace=%s)", len(normalized_tasks), trace_id)

        completed: dict[str, dict] = dict(prior_results or {})
        responses: dict[str, dict] = {}
        failed: dict[str, dict] = {}
        pending = {task.task_id: task for task in normalized_tasks}

        while pending:
            ready = [
                task
                for task in pending.values()
                if all(dep in completed for dep in task.depends_on)
            ]

            if not ready:
                skipped = list(pending.values())
                for task in skipped:
                    response = AgentResponse(
                        trace_id=trace_id,
                        agent_name=task.agent_name,
                        task_type=task.task_type,
                        status="skipped",
                        error={
                            "message": "Task dependencies were not satisfied",
                            "depends_on": task.depends_on,
                        },
                    )
                    failed[task.task_id] = response.model_dump()
                    responses[task.task_id] = response.model_dump()
                    pending.pop(task.task_id, None)
                break

            batch_results = await asyncio.gather(
                *[
                    self._run_task(
                        task=task,
                        trace_id=trace_id,
                        user_id=user_id,
                        session_id=session_id,
                        user_message=user_message,
                        user_profile=user_profile,
                        prior_results=completed,
                    )
                    for task in ready
                ]
            )

            for task, response in zip(ready, batch_results):
                response_dict = response.model_dump()
                responses[task.task_id] = response_dict
                if response.status in ("success", "partial"):
                    completed[task.task_id] = response_dict
                    # Also expose by agent name for backwards compatibility.
                    completed[task.agent_name] = response.result
                    logger.info("Task %s completed with status=%s", task.task_id, response.status)
                else:
                    failed[task.task_id] = response_dict
                    logger.warning("Task %s failed with status=%s", task.task_id, response.status)
                pending.pop(task.task_id, None)

        return {
            "completed": completed,
            "failed": failed,
            "responses": responses,
            "success": len(failed) == 0,
            "trace_id": trace_id,
        }

    def _normalize_task(self, task: dict | AgentTask) -> AgentTask:
        if isinstance(task, AgentTask):
            return task

        agent_name = task.get("agent_name") or task.get("agent")
        task_id = task.get("task_id") or agent_name
        return AgentTask(
            task_id=task_id,
            agent_name=agent_name,
            task_type=task.get("task_type", task.get("type", "default")),
            payload=task.get("payload", {}),
            depends_on=task.get("depends_on", []),
            required=task.get("required", False),
            timeout_seconds=task.get("timeout_seconds"),
            retry=task.get("retry", self.max_retries),
        )

    async def _run_task(
        self,
        task: AgentTask,
        trace_id: str,
        user_id: str,
        session_id: str,
        user_message: str,
        user_profile: dict,
        prior_results: dict,
    ) -> AgentResponse:
        agent = agent_registry.get(task.agent_name)
        if not agent:
            return AgentResponse(
                trace_id=trace_id,
                agent_name=task.agent_name,
                task_type=task.task_type,
                status="failed",
                error={"message": f"Agent {task.agent_name} not found"},
            )

        attempts = max(task.retry, 0) + 1
        timeout = task.timeout_seconds or self.timeout_seconds
        request = AgentRequest(
            trace_id=trace_id,
            user_id=user_id,
            session_id=session_id,
            agent_name=task.agent_name,
            task_type=task.task_type,
            user_message=user_message,
            payload=task.payload,
            user_profile=user_profile,
            prior_results=prior_results,
            deadline_ms=timeout * 1000,
        )

        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return await asyncio.wait_for(agent.handle(request), timeout=timeout)
            except asyncio.TimeoutError:
                return AgentResponse(
                    trace_id=trace_id,
                    agent_name=task.agent_name,
                    task_type=task.task_type,
                    status="timeout",
                    error={"message": f"Timeout after {timeout}s"},
                )
            except Exception as exc:
                last_error = exc
                logger.exception(
                    "Task %s attempt %d/%d failed", task.task_id, attempt, attempts
                )

        return AgentResponse(
            trace_id=trace_id,
            agent_name=task.agent_name,
            task_type=task.task_type,
            status="failed",
            error={
                "message": str(last_error) if last_error else "Unknown agent error",
                "type": last_error.__class__.__name__ if last_error else "UnknownError",
            },
        )


orchestrator = AgentOrchestrator()
