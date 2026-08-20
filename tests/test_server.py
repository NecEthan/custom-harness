"""Tests for the FastAPI SSE server.

Uses httpx AsyncClient with ASGI transport — no real network, no real Anthropic calls.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch

import harness.server as server_module
from harness.server import RunState, app
from harness.events import AgentFinished, AgentStarted


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_run_state():
    """Isolate each test — clear global run state before and after."""
    server_module._current_run = None
    yield
    server_module._current_run = None


@pytest.fixture
def client():
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

async def test_health(client):
    async with client as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /run
# ---------------------------------------------------------------------------

async def test_start_run_returns_202(client):
    async def noop(*args, **kwargs):
        pass

    with patch.object(server_module, "_execute_run", new=noop):
        async with client as c:
            r = await c.post("/run", json={"task": "list files"})
    assert r.status_code == 202
    assert r.json()["task"] == "list files"


async def test_start_run_sets_current_run(client):
    started = asyncio.Event()

    async def slow_noop(state, *args, **kwargs):
        started.set()
        await asyncio.sleep(0)

    with patch.object(server_module, "_execute_run", new=slow_noop):
        async with client as c:
            await c.post("/run", json={"task": "test task"})

    assert server_module._current_run is not None
    assert server_module._current_run.task == "test task"


# ---------------------------------------------------------------------------
# GET /run/state (polling fallback)
# ---------------------------------------------------------------------------

async def test_run_state_404_when_no_run(client):
    async with client as c:
        r = await c.get("/run/state")
    assert r.status_code == 404


async def test_run_state_returns_events(client):
    server_module._current_run = RunState(
        task="test",
        events=[{"type": "AgentStarted", "task": "test", "timestamp": 1.0}],
        done=True,
    )
    async with client as c:
        r = await c.get("/run/state")
    assert r.status_code == 200
    body = r.json()
    assert body["task"] == "test"
    assert body["done"] is True
    assert body["event_count"] == 1
    assert body["events"][0]["type"] == "AgentStarted"


# ---------------------------------------------------------------------------
# GET /run/events (SSE)
# ---------------------------------------------------------------------------

async def test_sse_404_when_no_run(client):
    async with client as c:
        r = await c.get("/run/events")
    assert r.status_code == 404


async def _collect_sse(client, path="/run/events") -> list[dict]:
    """Connect to an SSE endpoint and collect all data events until stream closes."""
    events = []
    async with client as c:
        async with c.stream("GET", path) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if line.startswith("data:"):
                    events.append(json.loads(line[5:].strip()))
    return events


async def test_sse_streams_accumulated_events(client):
    server_module._current_run = RunState(
        task="test",
        events=[
            {"type": "AgentStarted", "task": "test", "timestamp": 1.0},
            {"type": "AgentFinished", "total_turns": 1, "final_text": "done", "timestamp": 2.0},
        ],
        done=True,
    )
    events = await _collect_sse(client)
    assert len(events) == 2
    assert events[0]["type"] == "AgentStarted"
    assert events[1]["type"] == "AgentFinished"


async def test_sse_event_order_preserved(client):
    accumulated = [
        {"type": "AgentStarted", "task": "t", "timestamp": 1.0},
        {"type": "TurnStarted", "turn": 1, "timestamp": 1.1},
        {"type": "ModelCalled", "turn": 1, "model": "m", "message_count": 1, "tool_count": 0, "timestamp": 1.2},
        {"type": "ModelResponded", "turn": 1, "model": "m", "input_tokens": 10, "output_tokens": 5,
         "latency": 0.5, "stop_reason": "end_turn", "timestamp": 1.7},
        {"type": "TurnEnded", "turn": 1, "stop_reason": "end_turn", "text": "done", "timestamp": 1.8},
        {"type": "AgentFinished", "total_turns": 1, "final_text": "done", "timestamp": 1.9},
    ]
    server_module._current_run = RunState(task="t", events=accumulated, done=True)
    events = await _collect_sse(client)
    types = [e["type"] for e in events]
    assert types == ["AgentStarted", "TurnStarted", "ModelCalled", "ModelResponded", "TurnEnded", "AgentFinished"]


async def test_sse_agent_started_event(client):
    server_module._current_run = RunState(
        task="my task",
        events=[{"type": "AgentStarted", "task": "my task", "timestamp": 1.0}],
        done=True,
    )
    events = await _collect_sse(client)
    assert events[0]["type"] == "AgentStarted"
    assert events[0]["task"] == "my task"


async def test_sse_model_called_event(client):
    server_module._current_run = RunState(
        task="t",
        events=[
            {"type": "AgentStarted", "task": "t", "timestamp": 1.0},
            {"type": "ModelCalled", "turn": 1, "model": "claude-sonnet-4-6",
             "message_count": 1, "tool_count": 3, "timestamp": 1.1},
        ],
        done=True,
    )
    events = await _collect_sse(client)
    mc = next(e for e in events if e["type"] == "ModelCalled")
    assert mc["model"] == "claude-sonnet-4-6"
    assert mc["message_count"] == 1
    assert mc["tool_count"] == 3


async def test_sse_model_responded_event(client):
    server_module._current_run = RunState(
        task="t",
        events=[
            {"type": "ModelResponded", "turn": 1, "model": "claude-sonnet-4-6",
             "input_tokens": 3500, "output_tokens": 150, "latency": 1.23,
             "stop_reason": "end_turn", "timestamp": 2.0},
            {"type": "AgentFinished", "total_turns": 1, "final_text": "ok", "timestamp": 2.1},
        ],
        done=True,
    )
    events = await _collect_sse(client)
    mr = next(e for e in events if e["type"] == "ModelResponded")
    assert mr["input_tokens"] == 3500
    assert mr["output_tokens"] == 150
    assert mr["latency"] == pytest.approx(1.23)


async def test_sse_tool_called_event(client):
    server_module._current_run = RunState(
        task="t",
        events=[
            {"type": "ToolCalled", "turn": 1, "tool_use_id": "tid-1",
             "name": "read_file", "input": {"path": "src/auth.py"}, "timestamp": 1.5},
            {"type": "AgentFinished", "total_turns": 1, "final_text": "ok", "timestamp": 2.0},
        ],
        done=True,
    )
    events = await _collect_sse(client)
    tc = next(e for e in events if e["type"] == "ToolCalled")
    assert tc["name"] == "read_file"
    assert tc["input"] == {"path": "src/auth.py"}


async def test_sse_tool_resulted_event(client):
    server_module._current_run = RunState(
        task="t",
        events=[
            {"type": "ToolResulted", "turn": 1, "tool_use_id": "tid-1",
             "name": "read_file", "output": "file contents", "is_error": False,
             "duration": 0.05, "timestamp": 1.6},
            {"type": "AgentFinished", "total_turns": 1, "final_text": "ok", "timestamp": 2.0},
        ],
        done=True,
    )
    events = await _collect_sse(client)
    tr = next(e for e in events if e["type"] == "ToolResulted")
    assert tr["name"] == "read_file"
    assert not tr["is_error"]
    assert tr["duration"] == pytest.approx(0.05)


async def test_sse_agent_finished_event(client):
    server_module._current_run = RunState(
        task="t",
        events=[
            {"type": "AgentFinished", "total_turns": 3, "final_text": "Analysis complete.", "timestamp": 5.0},
        ],
        done=True,
    )
    events = await _collect_sse(client)
    af = next(e for e in events if e["type"] == "AgentFinished")
    assert af["total_turns"] == 3
    assert af["final_text"] == "Analysis complete."


async def test_sse_agent_failed_event(client):
    server_module._current_run = RunState(
        task="t",
        events=[
            {"type": "AgentFailed", "turn": 1, "error": "Connection timeout",
             "error_type": "TimeoutError", "timestamp": 2.0},
        ],
        done=True,
    )
    events = await _collect_sse(client)
    af = next(e for e in events if e["type"] == "AgentFailed")
    assert af["error_type"] == "TimeoutError"
    assert "timeout" in af["error"].lower()


async def test_sse_empty_run(client):
    server_module._current_run = RunState(task="t", events=[], done=True)
    events = await _collect_sse(client)
    assert events == []


async def test_sse_multiple_turns(client):
    server_module._current_run = RunState(
        task="t",
        events=[
            {"type": "AgentStarted", "task": "t", "timestamp": 0.0},
            {"type": "TurnStarted", "turn": 1, "timestamp": 0.1},
            {"type": "ModelResponded", "turn": 1, "model": "m", "input_tokens": 100,
             "output_tokens": 50, "latency": 1.0, "stop_reason": "tool_use", "timestamp": 1.1},
            {"type": "TurnEnded", "turn": 1, "stop_reason": "tool_use", "text": "", "timestamp": 1.2},
            {"type": "TurnStarted", "turn": 2, "timestamp": 1.3},
            {"type": "ModelResponded", "turn": 2, "model": "m", "input_tokens": 200,
             "output_tokens": 75, "latency": 0.8, "stop_reason": "end_turn", "timestamp": 2.1},
            {"type": "TurnEnded", "turn": 2, "stop_reason": "end_turn", "text": "done", "timestamp": 2.2},
            {"type": "AgentFinished", "total_turns": 2, "final_text": "done", "timestamp": 2.3},
        ],
        done=True,
    )
    events = await _collect_sse(client)
    assert len(events) == 8
    turn_started = [e for e in events if e["type"] == "TurnStarted"]
    assert len(turn_started) == 2
    assert turn_started[0]["turn"] == 1
    assert turn_started[1]["turn"] == 2
