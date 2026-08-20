"""Tests for shell tool."""

import pytest
from harness.registry import ToolRegistry
from harness.tools.shell import register_shell_tools


@pytest.fixture
def registry():
    r = ToolRegistry()
    register_shell_tools(r, timeout=5)
    return r


async def test_run_echo(registry):
    result = await registry.call("run_shell", "s1", {"command": "echo hello"})
    assert not result.is_error
    assert "hello" in result.output


async def test_exit_code_captured(registry):
    result = await registry.call("run_shell", "s2", {"command": "false"})
    assert not result.is_error          # tool itself didn't error
    assert "[exit 1]" in result.output


async def test_stderr_captured(registry):
    result = await registry.call("run_shell", "s3", {"command": "ls /nonexistent_xyz"})
    assert "[stderr]" in result.output


async def test_timeout(registry):
    r = ToolRegistry()
    register_shell_tools(r, timeout=1)
    result = await r.call("run_shell", "s4", {"command": "sleep 10"})
    assert not result.is_error
    assert "timeout" in result.output


async def test_empty_command(registry):
    result = await registry.call("run_shell", "s5", {"command": ""})
    assert not result.is_error
    assert "empty" in result.output


async def test_allowlist_blocks_command():
    r = ToolRegistry()
    register_shell_tools(r, allowed_commands=["echo"])
    result = await r.call("run_shell", "s6", {"command": "ls ."})
    assert result.is_error
    assert "not allowed" in result.output


async def test_allowlist_permits_command():
    r = ToolRegistry()
    register_shell_tools(r, allowed_commands=["echo"])
    result = await r.call("run_shell", "s7", {"command": "echo ok"})
    assert not result.is_error
    assert "ok" in result.output
