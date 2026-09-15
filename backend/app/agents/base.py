"""Base Agent class for LangGraph-based agents."""

from abc import ABC, abstractmethod
from typing import Any, Optional

from langgraph.graph import StateGraph

from app.agents.protocol import AgentRequest, AgentResponse


class AgentState(dict):
    """Base state schema for all agents.

    All agent states should extend this class.
    """
    pass


class BaseAgent(ABC):
    """Abstract base class for all health agents.

    Attributes:
        name: Unique agent identifier (e.g., "health_advisor")
        description: Human-readable description
        version: Agent version for compatibility
        graph: Compiled LangGraph instance
    """

    def __init__(
        self,
        name: str,
        description: str,
        version: str = "1.0.0",
    ):
        self.name = name
        self.description = description
        self.version = version
        self._graph: Optional[Any] = None

    @property
    def graph(self) -> Any:
        """Get or compile the LangGraph."""
        if self._graph is None:
            self._graph = self._compile_graph()
        return self._graph

    @abstractmethod
    def _compile_graph(self) -> Any:
        """Compile the StateGraph into a runnable.

        Returns:
            Compiled LangGraph instance
        """
        pass

    @abstractmethod
    async def process(self, state: AgentState) -> AgentState:
        """Main entry point for agent processing.

        Args:
            state: Current agent state

        Returns:
            Updated state with agent's response
        """
        pass

    async def handle(self, request: AgentRequest) -> AgentResponse:
        """Handle a standard agent request.

        Concrete agents can override this to translate the protocol request into
        their own LangGraph state. The default implementation supports simple
        dict-based agents and keeps older tests/agents compatible.
        """
        try:
            state = AgentState(request.payload)
            state["user_message"] = request.user_message or request.payload.get("message", "")
            state["user_id"] = request.user_id
            state["session_id"] = request.session_id
            state["user_profile"] = request.user_profile
            state["prior_results"] = request.prior_results
            result = await self.process(state)
            result_dict = dict(result)
            return AgentResponse(
                trace_id=request.trace_id,
                agent_name=request.agent_name,
                task_type=request.task_type,
                status="success" if result_dict.get("status") != "error" else "failed",
                result=result_dict,
                summary=result_dict.get("response", ""),
                citations=result_dict.get("citations", []),
                suggested_questions=result_dict.get("suggested_questions", []),
            )
        except Exception as exc:
            return AgentResponse(
                trace_id=request.trace_id,
                agent_name=request.agent_name,
                task_type=request.task_type,
                status="failed",
                error={"message": str(exc), "type": exc.__class__.__name__},
            )

    def get_info(self) -> dict:
        """Get agent metadata."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
        }
