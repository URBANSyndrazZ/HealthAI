import logging
from typing import Any, Dict

from langgraph.graph import END, StateGraph

from app.agents.base import BaseAgent, AgentState
from app.agents.protocol import AgentRequest, AgentResponse

from .nodes import assess_fitness, format_response, generate_plan, llm_refine_plan, safety_validate
from .state import ExerciseState

logger = logging.getLogger(__name__)

class ExerciseAgent(BaseAgent):
    """Agent for exercise and fitness planning.

    This agent provides personalized workout plans and fitness guidance:
    - Fitness level assessment
    - Personalized workout plans
    - Exercise data analysis
    - Injury prevention advice

    State Graph:
        assess_fitness → generate_plan → llm_refine_plan → safety_validate
        → format_response → END

    Attributes:
        name: Agent identifier
        description: Agent description
        state_class: State class for this agent
    """

    name = "exercise_agent"
    description = "Creates personalized workout plans and fitness recommendations"
    state_class = ExerciseState

    def __init__(self):
        """Initialize the exercise agent."""
        super().__init__(
            name="exercise_agent",
            description="Creates personalized workout plans and fitness recommendations",
            version="1.0.0",
        )
        self._graph: Any = None

    def _compile_graph(self) -> Any:
        """Build the LangGraph workflow for exercise planning.

        The workflow follows this sequence:
        1. assess_fitness - Assess user's fitness level
        2. generate_plan - Generate workout plan
        3. llm_refine_plan - Optionally refine with LLM + RAG guidelines
        4. safety_validate - Apply deterministic safety guardrails
        5. format_response - Format final response

        Returns:
            Compiled StateGraph workflow
        """
        logger.info("[ExerciseAgent] Building workflow")

        # Create workflow
        workflow = StateGraph(dict)

        # Add nodes
        workflow.add_node("assess_fitness", assess_fitness)
        workflow.add_node("generate_plan", generate_plan)
        workflow.add_node("llm_refine_plan", llm_refine_plan)
        workflow.add_node("safety_validate", safety_validate)
        workflow.add_node("format_response", format_response)

        # Define edges
        workflow.set_entry_point("assess_fitness")
        workflow.add_edge("assess_fitness", "generate_plan")
        workflow.add_edge("generate_plan", "llm_refine_plan")
        workflow.add_edge("llm_refine_plan", "safety_validate")
        workflow.add_edge("safety_validate", "format_response")
        workflow.add_edge("format_response", END)

        logger.info("[ExerciseAgent] Workflow built successfully")

        return workflow.compile()

    async def process(self, state: ExerciseState) -> dict[str, Any]:
        """Process an exercise planning request.

        Args:
            state: Initial ExerciseState with user input

        Returns:
            Dictionary with workout plan and recommendations
        """
        logger.info(f"[ExerciseAgent] Processing request from user {getattr(state, 'user_id', 'anonymous')}")
        logger.info(f"[ExerciseAgent] Message: {getattr(state, 'user_message', '')[:100]}...")

        try:
            graph = self.graph

            # Convert state to dict for LangGraph
            if isinstance(state, ExerciseState):
                state_dict = state.to_dict()
            else:
                state_dict = dict(state)

            # Run workflow
            result = await graph.ainvoke(state_dict)
            if not isinstance(result, dict):
                logger.warning(
                    "[ExerciseAgent] Workflow returned non-dict result: %r. Falling back to current state.",
                    result,
                )
                result = dict(state_dict)

            # Extract results
            response = result.get("response", "")
            workout_plan = result.get("workout_plan", {})
            exercises = result.get("exercises", [])
            safety_notes = result.get("safety_notes", [])
            rag_guidelines = result.get("rag_guidelines", [])

            logger.info(f"[ExerciseAgent] Processing complete. Plan type: {workout_plan.get('plan_type', 'unknown')}")

            # Return results
            return {
                "response": response,
                "workout_plan": workout_plan,
                "exercises": exercises,
                "safety_notes": safety_notes,
                "fitness_level": result.get("fitness_level", "beginner"),
                "fitness_goals": result.get("fitness_goals", []),
                "llm_refine_status": result.get("llm_refine_status", "not_run"),
                "llm_refine_rationale": result.get("llm_refine_rationale", ""),
                "safety_validation_status": result.get("safety_validation_status", ""),
                "rag_guidelines": rag_guidelines,
                "tool_trace": result.get("tool_trace", []),
                "citations": [
                     {
                         "source": "美国运动医学会(ACSM)运动指南",
                         "url": "https://www.acsm.org/"
                     }
                 ] + [
                     {
                         "source": doc.get("title") or doc.get("source") or "RAG运动指南",
                         "url": doc.get("source", ""),
                     }
                     for doc in rag_guidelines[:3]
                 ],
            }

        except Exception as e:
            logger.error(f"[ExerciseAgent] Processing error: {e}")
            import traceback
            logger.error(f"[ExerciseAgent] Traceback: {traceback.format_exc()}")
            return {
                "response": f"抱歉，在制定运动计划时遇到了技术问题。请稍后再试。\n\n错误信息：{str(e)}",
                "workout_plan": {},
                "exercises": [],
                "safety_notes": [],
                "tool_trace": [],
                "citations": [],
            }

    async def create_plan(self, goal: str, fitness_level: str, time_minutes: int, user_id: str = "anonymous") -> Dict[str, Any]:
        """Convenience method to create a workout plan.

        Args:
            goal: Fitness goal (e.g., "减脂", "增肌")
            fitness_level: Fitness level (beginner, intermediate, advanced)
            time_minutes: Available time in minutes
            user_id: User identifier

        Returns:
            Workout plan results
        """
        state = ExerciseState(
            user_message=f"我想要{goal}，适合{fitness_level}，{time_minutes}分钟",
            user_id=user_id,
        )
        state.fitness_level = fitness_level
        state.fitness_goals = [goal]
        state.time_available = time_minutes

        return await self.process(state)

    async def handle(self, request: AgentRequest) -> AgentResponse:
        """Handle a standardized orchestrator request."""
        goal = request.payload.get("goal")
        fitness_level = request.payload.get("fitness_level", "beginner")
        time_minutes = int(request.payload.get("time_minutes", 30))
        message = request.user_message or request.payload.get("message")
        if not message:
            message = f"我想要{goal or '健康'}，适合{fitness_level}，{time_minutes}分钟"

        state = ExerciseState(
            user_message=message,
            user_id=request.user_id,
            session_id=request.session_id,
        )
        state.fitness_level = fitness_level
        state.fitness_goals = [goal] if goal else []
        state.time_available = time_minutes
        state.user_profile = request.user_profile
        state["prior_results"] = request.prior_results
        state.prior_results = request.prior_results

        result = await self.process(state)
        status = "success" if result.get("response") else "failed"
        return AgentResponse(
            trace_id=request.trace_id,
            agent_name=request.agent_name,
            task_type=request.task_type,
            status=status,
            result=result,
            summary=result.get("response", ""),
            citations=result.get("citations", []),
            warnings=result.get("safety_notes", []),
            metadata={"tool_trace": result.get("tool_trace", [])},
        )
