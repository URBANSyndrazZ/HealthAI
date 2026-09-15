"""Agent Registry for managing agent instances."""

import logging
from typing import Optional, Type

from app.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """Central registry for agent management.

    Provides agent lookup by name and maintains agent instances.
    """

    def __init__(self):
        self._agents: dict[str, BaseAgent] = {}
        self._agent_classes: dict[str, Type[BaseAgent]] = {}

    def register_class(self, name: str, agent_class: Type[BaseAgent]) -> None:
        """Register an agent class without instantiating.

        Args:
            name: Unique agent identifier
            agent_class: Agent class (not instance)
        """
        self._agent_classes[name] = agent_class

    def register(self, name: str, agent: BaseAgent) -> None:
        """Register an agent instance.

        Args:
            name: Unique agent identifier
            agent: Initialized agent instance
        """
        self._agents[name] = agent

    def get(self, name: str) -> Optional[BaseAgent]:
        """Get an agent by name.

        Args:
            name: Agent identifier

        Returns:
            Agent instance or None if not found
        """
        # Return instance if available
        if name in self._agents:
            return self._agents[name]

        # Try to instantiate from registered class
        if name in self._agent_classes:
            agent_class = self._agent_classes[name]
            agent = agent_class()
            self._agents[name] = agent
            return agent

        return None

    def list_agents(self) -> list[str]:
        """List all registered agent names."""
        names = set(self._agents.keys())
        names.update(self._agent_classes.keys())
        return sorted(list(names))

    def get_info(self) -> list[dict]:
        """Get metadata for all registered agents."""
        info = []
        for name in self.list_agents():
            agent = self.get(name)
            if agent:
                info.append(agent.get_info())
        return info


# Import and register agents
def _register_agents():
    """Register all agents to the global registry."""
    try:
        # Register NutritionAgent
        from app.agents.nutrition import NutritionAgent
        agent_registry.register_class("nutrition", NutritionAgent)

        # Register EnvironmentAgent
        from app.agents.environment import EnvironmentAgent
        agent_registry.register_class("environment", EnvironmentAgent)

        # Register ExerciseAgent
        from app.agents.exercise import ExerciseAgent
        agent_registry.register_class("exercise", ExerciseAgent)

        logger.info(f"Registered agents: {agent_registry.list_agents()}")
    except Exception as e:
        logger.error(f"Failed to register agents: {e}")


# Global registry instance
agent_registry = AgentRegistry()

# Register agents on module load
_register_agents()
