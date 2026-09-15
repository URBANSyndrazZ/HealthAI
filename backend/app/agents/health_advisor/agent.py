import asyncio
import logging
from typing import Any

from langgraph.constants import END
from langgraph.graph import StateGraph

from app.agents.base import BaseAgent
from app.agents.health_advisor.nodes import (
    load_context, check_safety, urgent_reply, classify_intent, memory_route, retrieve_memory, plan_tasks,
    dispatch_agents, aggregate_results, rag_retrieve, generate_response, post_process
)

from app.models.database import async_session
from app.agents.health_advisor.state import HealthAdvisorState

logger = logging.getLogger(__name__)

class HealthAdvisorAgent(BaseAgent):
    """Health Advisor Agent for general health consultations.

        This agent handles:
        - General health questions
        - Lifestyle advice (diet, exercise, sleep)
        - Basic symptom information
        - Health education

        State Machine:
            load_context → check_safety → [urgent_reply | classify_intent]
            classify_intent → memory_route → retrieve_memory → plan_tasks
            plan_tasks → [dispatch_agents | rag_retrieve | generate_response]
            dispatch_agents → aggregate_results → [rag_retrieve | generate_response]
            rag_retrieve → generate_response → post_process
        """

    def __init__(self):
        super().__init__(
            name="health_advisor",
            description="健康顾问 - 处理一般健康咨询、生活方式建议和健康教育",
            version="1.0.0",
        )
        self._graph: Any = None

    def _compile_graph(self) -> Any:
        """Compile the LangGraph state machine."""

        # Create state graph - use dict for state
        workflow = StateGraph(dict)

        # Add nodes
        workflow.add_node("load_context", self._wrap_node(load_context))
        workflow.add_node("check_safety", check_safety)
        workflow.add_node("urgent_reply", urgent_reply)
        workflow.add_node("classify_intent", classify_intent)
        workflow.add_node("memory_route", memory_route)
        workflow.add_node("retrieve_memory", self._wrap_node(retrieve_memory))
        workflow.add_node("plan_tasks", plan_tasks)
        workflow.add_node("dispatch_agents", dispatch_agents)
        workflow.add_node("aggregate_results", aggregate_results)
        workflow.add_node("rag_retrieve", rag_retrieve)
        workflow.add_node("generate_response", generate_response)
        workflow.add_node("post_process", post_process)

        # Set entry point
        workflow.set_entry_point("load_context")

        # Add edges
        workflow.add_edge("load_context", "check_safety")

        # Conditional routing from safety check
        workflow.add_conditional_edges(
            "check_safety",
            self._route_after_safety,
            {
                "urgent": "urgent_reply",
                "normal": "classify_intent"
            }
        )

        # Urgent reply goes to post_process
        workflow.add_edge("urgent_reply", "post_process")

        # Normal flow
        workflow.add_edge("classify_intent", "memory_route")
        workflow.add_edge("memory_route", "retrieve_memory")
        workflow.add_edge("retrieve_memory", "plan_tasks")
        workflow.add_conditional_edges(
            "plan_tasks",
            self._route_after_planning_and_memory,
            {
                "dispatch": "dispatch_agents",
                "rag": "rag_retrieve",
                "generate": "generate_response"
            }
        )
        workflow.add_edge("dispatch_agents", "aggregate_results")
        workflow.add_conditional_edges(
            "aggregate_results",
            self._route_after_aggregation,
            {
                "rag": "rag_retrieve",
                "generate": "generate_response"
            }
        )
        workflow.add_edge("rag_retrieve", "generate_response")
        workflow.add_edge("generate_response", "post_process")

        # End after post_process
        workflow.add_edge("post_process", END)

        return workflow.compile()

    def _wrap_node(self, node_func):
        """Wrap a nodes function to inject dependencies"""
        async def wrapped(state: HealthAdvisorState):
            # Inject db session if needed
            if node_func.__name__ in {"load_context", "retrieve_memory"}:
                # Create a new db session for this nodes
                async with async_session() as db:
                    return await node_func(state, db)
            return await node_func(state)
        return wrapped

    def _route_after_safety(self, state: HealthAdvisorState) -> str:
        """Determine routing after safety check"""
        safety_flag = state.get("safety_flag", {})
        if safety_flag.get("is_urgent", False):
            return "urgent"
        return "normal"

    def _route_after_planning_and_memory(self, state: HealthAdvisorState) -> str:
        """Determine whether specialist agents or RAG are required after memory routing."""
        if state.get("sub_tasks"):
            return "dispatch"

        needs_rag = bool((state.get("memory_policy") or {}).get("needs_rag"))
        return "rag" if needs_rag else "generate"

    def _route_after_aggregation(self, state: HealthAdvisorState):
        """Determine whether RAG is still needed after specialist agent aggregation."""
        needs_rag = bool((state.get("memory_policy") or {}).get("needs_rag"))
        return "rag" if needs_rag else "generate"

    async def process(self, state: HealthAdvisorState) -> HealthAdvisorState:
        """Process user request through the agent.

        Args:
            state: Initial state with user message

        Returns:
            Final state with response
        """
        logger.info(f"Processing request: {state.user_message[:100]}...")

        try:
            # Get or compile graph
            graph = self.graph

            # Execute graph - convert state to dict for LangGraph
            initial_state_dict = dict(state)
            final_state_dict = await graph.ainvoke(initial_state_dict)

            # Convert result back to HealthAdvisorState
            final_state = HealthAdvisorState(**final_state_dict)

            logger.info("Request processing complete")

            return final_state
        except Exception as e:
            logger.error(f"Error in agent process: {e}", exc_info=True)
            # Return error response
            state["response"] = f"抱歉, 处理您的请求时出现了错误: {str(e)}"
            state["status"] = "error"
            return state