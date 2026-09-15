from typing import Callable, Optional

class Tool:
    """Represents a tool that can be invoked by agents."""

    def __init__(
        self,
        name: str,
        description: str,
        func: Callable,
        parameters: dict|None = None
    ):
        self.name = name
        self.description = description
        self.func = func
        self.parameters = parameters or {}

    async def invoke(self, **kwargs) -> str:
        """Invoke the tool with given arguments."""
        import inspect

        # Check if func is async
        if inspect.iscoroutinefunction(self.func):
            return await self.func(**kwargs)
        else:
            return self.func(**kwargs)

    def invoke_sync(self, **kwargs):
        """Invoke a synchronous tool from a synchronous workflow node."""
        import inspect

        if inspect.iscoroutinefunction(self.func):
            raise RuntimeError(f"Tool {self.name} is async and must be awaited")
        return self.func(**kwargs)

class ToolRegistry:
    """Registery for managing available tools."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, name: str, description: str, func: Callable, parameters: dict|None = None) -> Tool:
        """Register a new tool.

        Args:
            name: Unique tool identifier
            description: Human-readable description
            func: Function to invoke
            parameters: JSON Schema for parameters

        Returns:
            Registered tool instance
        """
        tool = Tool(name, description, func, parameters)
        self._tools[name] = tool
        return tool

    def get(self, name: str) -> Tool|None:
        """Get a tool by name."""
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """List all regitered tool names."""
        return sorted(list(self._tools.keys()))

    def get_schemas(self) -> list[dict]:
        """Get OpenAI-style function schemas for all tools."""
        schemas = []
        for name, tool in self._tools.items():
            schema = {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters
                }
            }
            schemas.append(schema)
        return schemas

# Global registry instance
tool_registry = ToolRegistry()
