"""Tool registry — maps names to async callables, owns schema list."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from harness.permissions import PermissionMode, ToolPermission, is_allowed


# ---------------------------------------------------------------------------
# Tool result
# ---------------------------------------------------------------------------

@dataclass
class ToolResult:
    tool_use_id: str
    output: str
    is_error: bool = False


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------

@dataclass
class ToolDefinition:
    name: str
    description: str
    input_schema: dict[str, Any]
    fn: Callable[..., Awaitable[str]]
    permission: ToolPermission = ToolPermission.READ  # minimum permission required to call this tool

    def to_api_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    def __init__(self, mode: PermissionMode = PermissionMode.DEFAULT) -> None:
        self._tools: dict[str, ToolDefinition] = {}
        self.mode = mode

    def register(self, definition: ToolDefinition) -> None:
        self._tools[definition.name] = definition

    def tool(
        self,
        name: str,
        description: str,
        input_schema: dict[str, Any],
        permission: ToolPermission = ToolPermission.READ,
    ) -> Callable:
        """Decorator for registering a tool."""
        def decorator(fn: Callable[..., Awaitable[str]]) -> Callable:
            self.register(ToolDefinition(
                name=name,
                description=description,
                input_schema=input_schema,
                fn=fn,
                permission=permission,
            ))
            return fn
        return decorator

    def schemas(self) -> list[dict[str, Any]]:
        """Return API schemas for tools allowed in the current mode."""
        return [
            t.to_api_schema()
            for t in self._tools.values()
            if is_allowed(self.mode, t.permission)
        ]

    async def call(self, name: str, tool_use_id: str, input_dict: dict[str, Any]) -> ToolResult:
        if name not in self._tools:
            return ToolResult(
                tool_use_id=tool_use_id,
                output=f"Unknown tool: {name}",
                is_error=True,
            )
        tool = self._tools[name]
        if not is_allowed(self.mode, tool.permission):
            return ToolResult(
                tool_use_id=tool_use_id,
                output=(
                    f"PermissionError: '{name}' requires {tool.permission.value!r} permission "
                    f"but current mode is {self.mode.value!r}"
                ),
                is_error=True,
            )
        try:
            output = await tool.fn(**input_dict)
            return ToolResult(tool_use_id=tool_use_id, output=output)
        except Exception as exc:
            return ToolResult(
                tool_use_id=tool_use_id,
                output=f"{type(exc).__name__}: {exc}",
                is_error=True,
            )
