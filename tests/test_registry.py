"""Tests for ToolRegistry."""

import pytest
from harness.registry import ToolDefinition, ToolRegistry


async def _echo(message: str) -> str:
    return message


@pytest.fixture
def registry():
    r = ToolRegistry()
    r.register(ToolDefinition(
        name="echo",
        description="Echo the message back.",
        input_schema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
        fn=_echo,
    ))
    return r


async def test_call_known_tool(registry):
    result = await registry.call("echo", "id-1", {"message": "hello"})
    assert result.output == "hello"
    assert not result.is_error
    assert result.tool_use_id == "id-1"


async def test_call_unknown_tool(registry):
    result = await registry.call("nope", "id-2", {})
    assert result.is_error
    assert "Unknown tool" in result.output


async def test_call_tool_raises(registry):
    async def boom(**kwargs) -> str:
        raise RuntimeError("exploded")

    registry.register(ToolDefinition(
        name="bomb",
        description="Always fails.",
        input_schema={"type": "object", "properties": {}, "required": []},
        fn=boom,
    ))
    result = await registry.call("bomb", "id-3", {})
    assert result.is_error
    assert "RuntimeError" in result.output
    assert "exploded" in result.output


def test_schemas(registry):
    schemas = registry.schemas()
    assert len(schemas) == 1
    assert schemas[0]["name"] == "echo"
    assert "input_schema" in schemas[0]
