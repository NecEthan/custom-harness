"""Tests for event serialization — the JSON bridge between Python events and React UI."""

import json
import pytest

from harness.events import (
    AgentFailed,
    AgentFinished,
    AgentStarted,
    ModelCalled,
    ModelResponded,
    ToolCalled,
    ToolResulted,
    TurnEnded,
    TurnStarted,
)
from harness.serialization import event_to_dict, event_to_json, sse_message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def all_events():
    return [
        AgentStarted(task="test task"),
        TurnStarted(turn=1),
        ModelCalled(turn=1, model="claude-sonnet-4-6", message_count=1, tool_count=3,
                    messages=({"role": "user", "content": "test task"},), tools=(), system="You are helpful."),
        ModelResponded(turn=1, model="claude-sonnet-4-6", input_tokens=100, output_tokens=50, latency=1.23, stop_reason="tool_use", content=()),
        ToolCalled(turn=1, tool_use_id="tid-1", name="read_file", input={"path": "src/main.py"}),
        ToolResulted(turn=1, tool_use_id="tid-1", name="read_file", output="content here", is_error=False, duration=0.05),
        ToolResulted(turn=1, tool_use_id="tid-2", name="broken_tool", output="RuntimeError: boom", is_error=True, duration=0.01),
        TurnEnded(turn=1, stop_reason="tool_use", text=""),
        AgentFinished(total_turns=2, final_text="done"),
        AgentFailed(turn=1, error="API timeout", error_type="TimeoutError"),
    ]


# ---------------------------------------------------------------------------
# Type field
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("event", all_events())
def test_type_field_matches_class_name(event):
    d = event_to_dict(event)
    assert d["type"] == type(event).__name__


# ---------------------------------------------------------------------------
# AgentStarted
# ---------------------------------------------------------------------------

def test_agent_started_serialization():
    event = AgentStarted(task="inspect codebase")
    d = event_to_dict(event)
    assert d["type"] == "AgentStarted"
    assert d["task"] == "inspect codebase"
    assert "timestamp" in d


# ---------------------------------------------------------------------------
# ModelCalled
# ---------------------------------------------------------------------------

def test_model_called_serialization():
    msgs = ({"role": "user", "content": "hi"},)
    tool_schemas = ({"name": "read_file", "description": "read", "input_schema": {}},)
    event = ModelCalled(turn=2, model="claude-sonnet-4-6", message_count=5, tool_count=4,
                        messages=msgs, tools=tool_schemas, system="Be helpful.")
    d = event_to_dict(event)
    assert d["type"] == "ModelCalled"
    assert d["turn"] == 2
    assert d["model"] == "claude-sonnet-4-6"
    assert d["message_count"] == 5
    assert d["tool_count"] == 4
    assert d["messages"] == msgs
    assert d["tools"] == tool_schemas
    assert d["system"] == "Be helpful."


# ---------------------------------------------------------------------------
# ModelResponded
# ---------------------------------------------------------------------------

def test_model_responded_serialization():
    from harness.adapter import TextBlock, ToolUseBlock
    blocks = (TextBlock(text="hello"), ToolUseBlock(tool_use_id="t1", name="greet", input={"name": "X"}))
    event = ModelResponded(
        turn=1,
        model="claude-sonnet-4-6",
        input_tokens=3500,
        output_tokens=150,
        latency=1.23,
        stop_reason="tool_use",
        content=blocks,
    )
    d = event_to_dict(event)
    assert d["type"] == "ModelResponded"
    assert d["input_tokens"] == 3500
    assert d["output_tokens"] == 150
    assert d["latency"] == pytest.approx(1.23)
    assert d["stop_reason"] == "tool_use"
    assert d["content"] == ({"text": "hello"}, {"tool_use_id": "t1", "name": "greet", "input": {"name": "X"}})


# ---------------------------------------------------------------------------
# ToolCalled
# ---------------------------------------------------------------------------

def test_tool_called_serialization():
    event = ToolCalled(turn=1, tool_use_id="tid-abc", name="read_file", input={"path": "src/auth.ts"})
    d = event_to_dict(event)
    assert d["type"] == "ToolCalled"
    assert d["name"] == "read_file"
    assert d["input"] == {"path": "src/auth.ts"}
    assert d["tool_use_id"] == "tid-abc"


# ---------------------------------------------------------------------------
# ToolResulted
# ---------------------------------------------------------------------------

def test_tool_resulted_success_serialization():
    event = ToolResulted(
        turn=1, tool_use_id="tid-1", name="read_file",
        output="file contents", is_error=False, duration=0.042,
    )
    d = event_to_dict(event)
    assert d["type"] == "ToolResulted"
    assert not d["is_error"]
    assert d["duration"] == pytest.approx(0.042)


def test_tool_resulted_error_serialization():
    event = ToolResulted(
        turn=1, tool_use_id="tid-2", name="write_file",
        output="PermissionError: denied", is_error=True, duration=0.001,
    )
    d = event_to_dict(event)
    assert d["is_error"] is True
    assert "PermissionError" in d["output"]


def test_tool_resulted_duration_none():
    event = ToolResulted(
        turn=1, tool_use_id="tid-3", name="greet",
        output="hi", is_error=False,
    )
    d = event_to_dict(event)
    assert d["duration"] is None


# ---------------------------------------------------------------------------
# AgentFinished
# ---------------------------------------------------------------------------

def test_agent_finished_serialization():
    event = AgentFinished(total_turns=4, final_text="Analysis complete.")
    d = event_to_dict(event)
    assert d["type"] == "AgentFinished"
    assert d["total_turns"] == 4
    assert d["final_text"] == "Analysis complete."


# ---------------------------------------------------------------------------
# AgentFailed
# ---------------------------------------------------------------------------

def test_agent_failed_serialization():
    event = AgentFailed(turn=2, error="Connection refused", error_type="ConnectionError")
    d = event_to_dict(event)
    assert d["type"] == "AgentFailed"
    assert d["turn"] == 2
    assert d["error"] == "Connection refused"
    assert d["error_type"] == "ConnectionError"


def test_agent_failed_no_turn():
    event = AgentFailed(turn=None, error="startup error", error_type="ValueError")
    d = event_to_dict(event)
    assert d["turn"] is None


# ---------------------------------------------------------------------------
# JSON output
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("event", all_events())
def test_event_to_json_is_valid_json(event):
    raw = event_to_json(event)
    parsed = json.loads(raw)
    assert parsed["type"] == type(event).__name__


# ---------------------------------------------------------------------------
# SSE message format
# ---------------------------------------------------------------------------

def test_sse_message_format():
    event = AgentStarted(task="hello")
    msg = sse_message(event)
    assert msg.startswith("data: ")
    assert msg.endswith("\n\n")
    payload = json.loads(msg[6:].strip())
    assert payload["type"] == "AgentStarted"


@pytest.mark.parametrize("event", all_events())
def test_sse_message_valid_for_all_events(event):
    msg = sse_message(event)
    assert msg.startswith("data: ")
    assert msg.endswith("\n\n")
