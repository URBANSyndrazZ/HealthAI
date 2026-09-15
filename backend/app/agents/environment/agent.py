import logging
from typing import Any, Dict

from langgraph.graph import END, StateGraph

from app.agents.base import BaseAgent, AgentState
from app.agents.protocol import AgentRequest, AgentResponse

from .nodes import (
    assess_risk,
    fetch_air_quality,
    fetch_weather,
    format_response,
    generate_advice,
    llm_generate_advice,
    resolve_location,
)
from .state import EnvironmentState

logger = logging.getLogger(__name__)

class EnvironmentAgent(BaseAgent):
    name = "environment_agent"
    description = "Analyzes environmental conditions and provides health recommendations"
    state_class = EnvironmentState

    def __init__(self):
        """Initialize the environment agent."""
        super().__init__(
            name="environment_agent",
            description="Analyzes environmental conditions and provides health recommendations",
            version="1.0.0",
        )
        self._graph = None

    def _compile_graph(self) -> Any:
        """Build the LangGraph workflow for environment analysis.

        The workflow follows this sequence:
        1. resolve_location - Parse and resolve user location
        2. fetch_air_quality - Get air quality data
        3. fetch_weather - Get weather data
        4. assess_risk - Assess health risks
        5. generate_advice - Generate recommendations
        6. llm_generate_advice - Optionally personalize wording with LLM
        7. format_response - Format final response

        Returns:
            Compiled StateGraph workflow
        """
        logger.info("[EnvironmentAgent] Building workflow")

        # Create workflow
        workflow = StateGraph(dict)

        # Add nodes
        workflow.add_node("resolve_location", resolve_location)
        workflow.add_node("fetch_air_quality", fetch_air_quality)
        workflow.add_node("fetch_weather", fetch_weather)
        workflow.add_node("assess_risk", assess_risk)
        workflow.add_node("generate_advice", generate_advice)
        workflow.add_node("llm_generate_advice", llm_generate_advice)
        workflow.add_node("format_response", format_response)

        # Define edges
        workflow.set_entry_point("resolve_location")
        workflow.add_edge("resolve_location", "fetch_air_quality")
        workflow.add_edge("fetch_air_quality", "fetch_weather")
        workflow.add_edge("fetch_weather", "assess_risk")
        workflow.add_edge("assess_risk", "generate_advice")
        workflow.add_edge("generate_advice", "llm_generate_advice")
        workflow.add_edge("llm_generate_advice", "format_response")
        workflow.add_edge("format_response", END)

        logger.info("[EnvironmentAgent] Workflow built successfully")

        return workflow.compile()

    async def process(self, state: EnvironmentState) -> dict[str, Any]:
        """Process an environment analysis request.

        This method runs the complete environment analysis workflow
        and returns the final results.

        Args:
            state: Initial EnvironmentState with user input

        Returns:
            Dictionary with analysis results including:
            - response: Formatted response text
            - location: Location information
            - air_quality: Air quality data
            - weather: Weather data
            - health_risk: Risk assessment
            - recommendations: List of recommendations
        """
        logger.info(f"[EnvironmentAgent] Processing request from user {getattr(state, 'user_id', 'anonymous')}")
        logger.info(f"[EnvironmentAgent] Message: {getattr(state, 'user_message', '')[:100]}...")

        try:
            # Build workflow
            graph = self.graph

            # Convert state to dict for LangGraph
            if isinstance(state, EnvironmentState):
                state_dict = state.to_dict()
            else:
                state_dict = dict(state)

            # Run workflow
            result = await graph.ainvoke(state_dict)

            # Extract results
            response = result.get("response", "")
            location = result.get("location", {})
            air_quality = result.get("air_quality", {})
            weather = result.get("weather", {})
            health_risk = result.get("health_risk", {})
            recommendations = result.get("recommendations", [])
            llm_advice = result.get("llm_advice", "")

            logger.info(f"[EnvironmentAgent] Processing complete. Location: {location.get('city', 'unknown')}")

            # Return results
            return {
                "response": response,
                "location": location,
                "air_quality": air_quality,
                "weather": weather,
                "health_risk": health_risk,
                "recommendations": recommendations,
                "llm_advice": llm_advice,
                "llm_advice_status": result.get("llm_advice_status", "not_run"),
                "tool_trace": result.get("tool_trace", []),
                "citations": [
                    {
                        "source": "中国环境监测总站",
                        "url": "https://www.cnemc.cn/"
                    }
                ],
            }

        except Exception as e:
            logger.error(f"[EnvironmentAgent] Processing error: {e}")
            import traceback
            logger.error(f"[EnvironmentAgent] Traceback: {traceback.format_exc()}")
            return {
                "response": f"抱歉，在获取环境数据时遇到了技术问题。请稍后再试，或尝试指定其他城市。\n\n错误信息：{str(e)}",
                "location": {},
                "air_quality": {},
                "weather": {},
                "health_risk": {},
                "recommendations": [],
                "tool_trace": [],
                "citations": [],
            }

    async def query_environment(self, location_query: str, user_id: str = "anonymous") -> Dict[str, Any]:
        """Convenience method to query environment data.

        Args:
            location_query: Location query (e.g., "北京市")
            user_id: User identifier

        Returns:
            Environment analysis results
        """
        state = EnvironmentState(
            user_message=f"查询{location_query}的环境健康信息",
            user_id=user_id,
        )
        state.location_query = location_query
        return await self.process(state)

    async def handle(self, request: AgentRequest) -> AgentResponse:
        """Handle a standardized orchestrator request."""
        location = (
            request.payload.get("location")
            or request.payload.get("location_query")
            or request.user_message
        )
        state = EnvironmentState(
            user_message=request.user_message or f"查询{location}的环境健康信息",
            user_id=request.user_id,
            session_id=request.session_id,
        )
        state.location_query = location or ""
        result = await self.process(state)
        status = "success" if result.get("response") else "failed"
        warnings = []
        health_risk = result.get("health_risk") or {}
        warnings.extend(health_risk.get("warnings", []))
        return AgentResponse(
            trace_id=request.trace_id,
            agent_name=request.agent_name,
            task_type=request.task_type,
            status=status,
            result=result,
            summary=result.get("response", ""),
            citations=result.get("citations", []),
            warnings=warnings,
            metadata={"tool_trace": result.get("tool_trace", [])},
        )