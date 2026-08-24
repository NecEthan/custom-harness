"""Tests for ToolRegistry."""

import pytest
from harness.permissions import PermissionMode, ToolPermission
from harness.registry import ToolDefinition, ToolRegistry


async def _echo(message: str) -> str:
    return message


async def _noop(**kwargs) -> str:
    return "ok"


def make_tool(name: str, permission: ToolPermission = ToolPermission.READ) -> ToolDefinition:
    return ToolDefinition(
        name=name,
        description=f"{name} tool",
        input_schema={"type": "object", "properties": {}, "required": []},
        fn=_noop,
        permission=permission,
    )


@pytest.fixture
def registry():
    r = ToolRegistry(mode=PermissionMode.BYPASS)
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


# ---------------------------------------------------------------------------
# Permission enforcement
# ---------------------------------------------------------------------------

async def test_blocked_tool_returns_permission_error():
    r = ToolRegistry(mode=PermissionMode.DEFAULT)
    r.register(make_tool("writer", ToolPermission.EDIT))
    result = await r.call("writer", "id-p1", {})
    assert result.is_error
    assert "PermissionError" in result.output
    assert "edit" in result.output
    assert "default" in result.output


async def test_allowed_tool_succeeds():
    r = ToolRegistry(mode=PermissionMode.DEFAULT)
    r.register(make_tool("reader", ToolPermission.READ))
    result = await r.call("reader", "id-p2", {})
    assert not result.is_error


async def test_bypass_allows_all_permissions():
    r = ToolRegistry(mode=PermissionMode.BYPASS)
    r.register(make_tool("shell", ToolPermission.EXECUTE))
    r.register(make_tool("writer", ToolPermission.EDIT))
    r.register(make_tool("reader", ToolPermission.READ))
    for name, tid in [("shell", "p3"), ("writer", "p4"), ("reader", "p5")]:
        result = await r.call(name, tid, {})
        assert not result.is_error, f"{name} should be allowed in BYPASS"


async def test_accept_edits_blocks_execute():
    r = ToolRegistry(mode=PermissionMode.ACCEPT_EDITS)
    r.register(make_tool("shell", ToolPermission.EXECUTE))
    result = await r.call("shell", "p6", {})
    assert result.is_error
    assert "execute" in result.output


async def test_accept_edits_allows_edit():
    r = ToolRegistry(mode=PermissionMode.ACCEPT_EDITS)
    r.register(make_tool("writer", ToolPermission.EDIT))
    result = await r.call("writer", "p7", {})
    assert not result.is_error


async def test_plan_blocks_edit_and_execute():
    r = ToolRegistry(mode=PermissionMode.PLAN)
    r.register(make_tool("writer", ToolPermission.EDIT))
    r.register(make_tool("shell", ToolPermission.EXECUTE))
    for name, tid in [("writer", "p8"), ("shell", "p9")]:
        result = await r.call(name, tid, {})
        assert result.is_error, f"{name} should be blocked in PLAN"


def test_schemas_filtered_by_mode():
    r = ToolRegistry(mode=PermissionMode.DEFAULT)
    r.register(make_tool("reader", ToolPermission.READ))
    r.register(make_tool("writer", ToolPermission.EDIT))
    r.register(make_tool("shell", ToolPermission.EXECUTE))
    schemas = r.schemas()
    names = [s["name"] for s in schemas]
    assert "reader" in names
    assert "writer" not in names
    assert "shell" not in names


def test_schemas_bypass_shows_all():
    r = ToolRegistry(mode=PermissionMode.BYPASS)
    r.register(make_tool("reader", ToolPermission.READ))
    r.register(make_tool("writer", ToolPermission.EDIT))
    r.register(make_tool("shell", ToolPermission.EXECUTE))
    assert len(r.schemas()) == 3
