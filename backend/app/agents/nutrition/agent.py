import logging
from typing import Any, Dict, Optional

from langgraph.graph import END, StateGraph

from app.agents.base import BaseAgent, AgentState
from app.agents.protocol import AgentRequest, AgentResponse

from .nodes import (
    analyze_nutrition,
    extract_food,
    format_response,
    generate_recommendations,
    parse_input,
    query_nutrition,
)
from .state import NutritionState
from ...models import user

logger = logging.getLogger(__name__)


class NutritionAgent(BaseAgent):
    """Agent for nutrition analysis and dietary recommendations.

    This agent analyzes food descriptions, extracts food items,
    queries nutrition data, analyzes nutritional composition,
    and generates personalized recommendations.

    State Graph:
        parse_input → extract_food → query_nutrition → analyze_nutrition
        → generate_recommendations → format_response → END

    Attributes:
        name: Agent identifier
        description: Agent description
        state_class: State class for this agent
    """
    name = "nutrition_agent"
    description = "Analyzes food nutrition and provides dietary recommendations"
    state_class = NutritionState

    def __init__(self):
        super().__init__(
            name="nutrition_agent",
            description="Analyzes food nutrition and provides dietary recommendations",
            version="1.0.0",
        )
        self._graph: Any = None

    def _compile_graph(self) -> Any:
        logger.info("[NutritionAgent] Building workflow")

        # Create workflow
        workflow = StateGraph(dict)

        # Add nodes
        workflow.add_node("parse_input", parse_input)
        workflow.add_node("extract_food", extract_food)
        workflow.add_node("query_nutrition", query_nutrition)
        workflow.add_node("analyze_nutrition", analyze_nutrition)
        workflow.add_node("generate_recommendations", generate_recommendations)
        workflow.add_node("format_response", format_response)

        # Define edges (linear flow)
        workflow.set_entry_point("parse_input")
        workflow.add_edge("parse_input", "extract_food")
        workflow.add_edge("extract_food", "query_nutrition")
        workflow.add_edge("query_nutrition", "analyze_nutrition")
        workflow.add_edge("analyze_nutrition", "generate_recommendations")
        workflow.add_edge("generate_recommendations", "format_response")
        workflow.add_edge("format_response", END)

        logger.info("[NutritionAgent] Workflow built successfully")

        return workflow.compile()

    async def process(self, state: NutritionState) -> dict[str, Any]:
        """Process a nutrition analysis request.

        This method runs the complete nutrition analysis workflow
        and returns the final results.

        Args:
            state: Initial NutritionState with user input

        Returns:
            Dictionary with analysis results including:
            - response: Formatted response text
            - nutrition_data: Detailed nutrition breakdown
            - health_score: Overall health score
            - recommendations: List of recommendations
            - citations: Source citations
        """
        logger.info(f"[NutritionAgent] Processing request from user {getattr(state, 'user_id', 'anonymous')}")
        logger.info(f"[NutritionAgent] Message: {getattr(state, 'user_message', '')[:100]}...")

        try:
            # Get or compile graph
            graph = self.graph

            # Convert state to dict for LangGraph
            if isinstance(state, NutritionState):
                state_dict = state.to_dict()
            else:
                state_dict = dict(state)

            result = await graph.ainvoke(state_dict)
            if not isinstance(result, dict):
                logger.warning(
                "[NutritionAgent] Workflow returned non-dict result: %r. Falling back to current state.",
                result,
                )
                result = dict(state_dict)

            # Extract results
            response = result.get("response", "")
            health_score = result.get("health_score", 0)
            recommendations = result.get("recommendations", [])

            logger.info(f"[NutritionAgent] Processing complete. Health score: {health_score}")

            # Return results
            return {
                "response": response,
                "nutrition_data": result.get("nutrition_data", {}),
                "total_nutrition": result.get("total_nutrition", {}),
                "health_score": health_score,
                "nutrition_analysis": result.get("nutrition_analysis", ""),
                "recommendations": recommendations,
                "alternative_foods": result.get("alternative_foods", []),
                "extracted_foods": result.get("extracted_foods", []),
                "tool_trace": result.get("tool_trace", []),
                "citations": [
                    {
                        "source": "中国食物成分表",
                        "url": "https://www.cfsn.cn/"
                    }
                ]
            }

        except Exception as e:
            logger.error(f"[NutritionAgent] Processing error: {e}")
            import traceback
            logger.error(f"[NutritionAgent] Traceback: {traceback.format_exc()}")
            return {
                "response": f"抱歉，在分析您的饮食时遇到了技术问题。请稍后再试，或者尝试用不同的方式描述您的饮食。\n\n错误信息：{str(e)}",
                "health_score": 0,
                "recommendations": [],
                "tool_trace": [],
                "citations": [],
            }

    async def analyze_meal(self, description: str, user_id: str = "anonymous") -> Dict[str, Any]:
        """Convenience method to analyze a meal.

        Args:
            description: Description of the meal
            user_id: User identifier

        Returns:
            Analysis results
        """
        state = NutritionState(
            user_message=description,
            user_id=user_id,
        )
        return await self.process(state)

    async def handle(self, request: AgentRequest) -> AgentResponse:
        """Handle a standardized orchestrator request."""
        message = request.user_message or request.payload.get("description") or request.payload.get("message") or ""
        result = await self.process(
            NutritionState(
                user_message=message,
                user_id=request.user_id,
                session_id=request.session_id,
            )
        )
        status = "failed" if not result.get("response") and result.get("health_score", 0) == 0 else "success"
        return AgentResponse(
            trace_id=request.trace_id,
            agent_name=request.agent_name,
            task_type=request.task_type,
            status=status,
            result=result,
            summary=result.get("response", ""),
            confidence=result.get("food_confidence"),
            citations=result.get("citations", []),
            warnings=[] if status == "success" else ["营养分析结果可能不完整"],
            metadata={"tool_trace": result.get("tool_trace", [])},
        )