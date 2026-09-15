from typing import Any

from app.agents.base import AgentState


class HealthAdvisorState(AgentState):
    """State schema for Health Advisor Agent.

    Fields:
        user_id: User identifier
        session_id: Session identifier
        user_message: Current user input
        context: Additional context (profile, memories, etc.)

        # Processing state
        intent: Classified intent
        retrieved_docs: RAG retrieved documents
        safety_flag: Safety concern flag

        # Output
        response: Generated response
        citations: Citations for the response
        suggested_questions: Follow-up questions

        # Control
        next_node: Next nodes to route to
    """
    def __init__(
        self,
        user_id: str = "",
        session_id: str = "",
        user_message: str = "",
        context: dict|None = None,
        **kwargs,
    ):
        super().__init__()
        self["user_id"] = user_id
        self["session_id"] = session_id
        self["user_message"] = user_message
        self["context"] = context or {}

        # Processing state
        self["intent"] = ""
        self["retrieved_docs"] = []
        self["safety_flag"] = None
        self["sub_tasks"] = []
        self["sub_agent_results"] = {}
        self["agent_trace"] = {}
        self["agent_warnings"] = []
        self["tool_trace"] = []
        self["assembled_context"] = {}
        self["context_trace"] = {}
        self["prompt_security"] = {"risk_level": "low", "is_suspicious": False, "categories": []}
        self["orchestration_status"] = "not_required"
        self["memory_policy"] = {
            "scope": "rag_only",
            "needs_short_term": False,
            "needs_long_term": False,
            "needs_rag": True,
            "reason": "",
        }
        self["memory_route_reason"] = ""
        self["retrieved_short_term_memories"] = []
        self["retrieved_long_term_memories"] = []

        # Output
        self["response"] = ""
        self["citations"] = []
        self["suggested_questions"] = []

        # Control
        self["next_node"] = ""

        # Update with any additional kwargs
        self.update(kwargs)

    @property
    def user_id(self) -> str:
        return self.get("user_id", "")

    @property
    def session_id(self) -> str:
        return self.get("session_id", "")

    @property
    def user_message(self) -> str:
        return self.get("user_message", "")

    @property
    def intent(self) -> str:
        return self.get("intent", "")

    @property
    def response(self) -> str:
        return self.get("response", "")

    @property
    def context(self) -> dict:
        return self.get("context", {})

    @property
    def retrieved_docs(self) -> list:
        return self.get("retrieved_docs", [])

    @property
    def safety_flag(self) -> Any:
        return self.get("safety_flag")

    @property
    def sub_tasks(self) -> list:
        return self.get("sub_tasks", [])

    @property
    def sub_agent_results(self) -> dict:
        return self.get("sub_agent_results", {})