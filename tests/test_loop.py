"""Tests for AgentLoop — adapter mocked, no real API calls."""

import pytest
from unittest.mock import AsyncMock, patch

from harness.adapter import ModelResponse, TextBlock, ToolUseBlock
from harness.events import (
    AgentFailed,
    AgentFinished,
    AgentStarted,
    EventBus,
    ModelCalled,
    ModelResponded,
    ToolCalled,
    ToolResulted,
    TurnEnded,
    TurnStarted,
)
from harness.loop import AgentLoop, LoopConfig
from harness.registry import ToolDefinition, ToolRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_text_response(text: str, input_tokens: int = 10, output_tokens: int = 5) -> ModelResponse:
    return ModelResponse(
        stop_reason="end_turn",
        content=[TextBlock(text=text)],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def make_tool_response(name: str, tool_id: str, input_dict: dict, input_tokens: int = 20, output_tokens: int = 10) -> ModelResponse:
    return ModelResponse(
        stop_reason="tool_use",
        content=[ToolUseBlock(tool_use_id=tool_id, name=name, input=input_dict)],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def collect_bus() -> tuple[EventBus, list]:
    """Return (bus, events_list) — events_list grows as events are emitted."""
    events = []

    async def collect(event):
        events.append(event)

    bus = EventBus()
    bus.subscribe(collect)
    return bus, events


def events_of(events: list, cls) -> list:
    return [e for e in events if isinstance(e, cls)]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def registry():
    r = ToolRegistry()
    r.register(ToolDefinition(
        name="greet",
        description="Say hello.",
        input_schema={
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "required": ["name"],
        },
        fn=AsyncMock(return_value="Hello, Alice!"),
    ))
    return r


# ---------------------------------------------------------------------------
# Basic correctness (pre-existing, updated for response.text() fix)
# ---------------------------------------------------------------------------

async def test_single_turn_no_tools(registry):
    loop = AgentLoop(registry)
    with patch.object(loop._adapter, "complete", new=AsyncMock(
        return_value=make_text_response("Done.")
    )):
        result = await loop.run("Say done.")

    assert result.final_text == "Done."
    assert result.total_turns == 1
    assert result.stop_reason == "end_turn"
    assert result.total_input_tokens == 10
    assert result.total_output_tokens == 5


async def test_tool_use_then_end(registry):
    responses = [
        make_tool_response("greet", "tid-1", {"name": "Alice"}),
        make_text_response("All done."),
    ]
    loop = AgentLoop(registry)
    with patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=responses)):
        result = await loop.run("Greet Alice.")

    assert result.final_text == "All done."
    assert result.total_turns == 2
    assert result.stop_reason == "end_turn"


async def test_max_turns_respected(registry):
    config = LoopConfig(max_turns=2)
    loop = AgentLoop(registry, config=config)
    with patch.object(loop._adapter, "complete", new=AsyncMock(
        return_value=make_tool_response("greet", "tid-x", {"name": "Bob"}),
    )):
        result = await loop.run("Loop forever.")

    assert result.total_turns == 2
    assert result.stop_reason == "max_turns"


# ---------------------------------------------------------------------------
# AgentStarted
# ---------------------------------------------------------------------------

async def test_agent_started_emitted(registry):
    bus, events = collect_bus()
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(
        return_value=make_text_response("ok")
    )):
        await loop.run("my task")

    started = events_of(events, AgentStarted)
    assert len(started) == 1
    assert started[0].task == "my task"


async def test_agent_started_is_first_event(registry):
    bus, events = collect_bus()
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(
        return_value=make_text_response("ok")
    )):
        await loop.run("task")

    assert isinstance(events[0], AgentStarted)


# ---------------------------------------------------------------------------
# TurnStarted
# ---------------------------------------------------------------------------

async def test_turn_started_emitted(registry):
    bus, events = collect_bus()
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(
        return_value=make_text_response("done")
    )):
        await loop.run("task")

    started = events_of(events, TurnStarted)
    assert len(started) == 1
    assert started[0].turn == 1


async def test_turn_started_per_turn(registry):
    bus, events = collect_bus()
    responses = [
        make_tool_response("greet", "t1", {"name": "X"}),
        make_text_response("done"),
    ]
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=responses)):
        await loop.run("task")

    started = events_of(events, TurnStarted)
    assert len(started) == 2
    assert [e.turn for e in started] == [1, 2]


# ---------------------------------------------------------------------------
# ModelCalled
# ---------------------------------------------------------------------------

async def test_model_called_emitted(registry):
    bus, events = collect_bus()
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(
        return_value=make_text_response("ok")
    )):
        await loop.run("task")

    called = events_of(events, ModelCalled)
    assert len(called) == 1
    assert called[0].turn == 1
    assert called[0].model == loop.config.adapter.model


async def test_model_called_captures_message_and_tool_counts(registry):
    bus, events = collect_bus()
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(
        return_value=make_text_response("ok")
    )):
        await loop.run("task")

    called = events_of(events, ModelCalled)[0]
    # Initial messages list has 1 entry (the user task)
    assert called.message_count == 1
    # Registry has one tool ("greet")
    assert called.tool_count == 1


async def test_model_called_emitted_each_turn(registry):
    bus, events = collect_bus()
    responses = [
        make_tool_response("greet", "t1", {"name": "X"}),
        make_text_response("done"),
    ]
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=responses)):
        await loop.run("task")

    called = events_of(events, ModelCalled)
    assert len(called) == 2
    assert called[0].turn == 1
    assert called[1].turn == 2
    # Turn 2 has more messages (user + assistant + tool_results)
    assert called[1].message_count > called[0].message_count


async def test_model_called_carries_full_payload(registry):
    bus, events = collect_bus()
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(
        return_value=make_text_response("ok")
    )):
        await loop.run("test task")

    called = events_of(events, ModelCalled)[0]
    # messages tuple contains the actual message dicts
    assert isinstance(called.messages, tuple)
    assert len(called.messages) == called.message_count
    assert called.messages[0]["role"] == "user"
    assert called.messages[0]["content"] == "test task"
    # tools tuple contains actual tool schemas
    assert isinstance(called.tools, tuple)
    assert len(called.tools) == called.tool_count
    # system prompt present
    assert called.system == loop.config.adapter.system


# ---------------------------------------------------------------------------
# ModelResponded
# ---------------------------------------------------------------------------

async def test_model_responded_emitted(registry):
    bus, events = collect_bus()
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(
        return_value=make_text_response("ok", input_tokens=15, output_tokens=7)
    )):
        await loop.run("task")

    responded = events_of(events, ModelResponded)
    assert len(responded) == 1
    r = responded[0]
    assert r.turn == 1
    assert r.model == loop.config.adapter.model
    assert r.input_tokens == 15
    assert r.output_tokens == 7
    assert r.stop_reason == "end_turn"


async def test_model_responded_latency_recorded(registry):
    bus, events = collect_bus()
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(
        return_value=make_text_response("ok")
    )):
        await loop.run("task")

    responded = events_of(events, ModelResponded)
    assert len(responded) == 1
    # Latency must be a non-negative float
    assert isinstance(responded[0].latency, float)
    assert responded[0].latency >= 0.0


async def test_model_responded_per_turn(registry):
    bus, events = collect_bus()
    responses = [
        make_tool_response("greet", "t1", {"name": "X"}, input_tokens=20, output_tokens=10),
        make_text_response("done", input_tokens=30, output_tokens=5),
    ]
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=responses)):
        await loop.run("task")

    responded = events_of(events, ModelResponded)
    assert len(responded) == 2
    assert responded[0].input_tokens == 20
    assert responded[0].output_tokens == 10
    assert responded[1].input_tokens == 30
    assert responded[1].output_tokens == 5


async def test_model_responded_carries_full_content(registry):
    bus, events = collect_bus()
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(
        return_value=make_text_response("hello world")
    )):
        await loop.run("task")

    responded = events_of(events, ModelResponded)[0]
    assert isinstance(responded.content, tuple)
    assert len(responded.content) > 0
    from harness.adapter import TextBlock
    assert any(isinstance(b, TextBlock) and b.text == "hello world" for b in responded.content)


async def test_model_responded_tool_use_content(registry):
    bus, events = collect_bus()
    responses = [
        make_tool_response("greet", "tid-x", {"name": "A"}),
        make_text_response("done"),
    ]
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=responses)):
        await loop.run("task")

    from harness.adapter import ToolUseBlock
    responded = events_of(events, ModelResponded)
    first = responded[0]
    assert any(isinstance(b, ToolUseBlock) and b.name == "greet" for b in first.content)


# ---------------------------------------------------------------------------
# ToolCalled / ToolResulted
# ---------------------------------------------------------------------------

async def test_tool_called_emitted(registry):
    bus, events = collect_bus()
    responses = [
        make_tool_response("greet", "tid-2", {"name": "Eve"}),
        make_text_response("Hi Eve."),
    ]
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=responses)):
        await loop.run("Greet Eve.")

    called = events_of(events, ToolCalled)
    assert len(called) == 1
    assert called[0].name == "greet"
    assert called[0].input == {"name": "Eve"}
    assert called[0].tool_use_id == "tid-2"


async def test_tool_resulted_emitted(registry):
    bus, events = collect_bus()
    responses = [
        make_tool_response("greet", "tid-3", {"name": "Bob"}),
        make_text_response("done"),
    ]
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=responses)):
        await loop.run("task")

    resulted = events_of(events, ToolResulted)
    assert len(resulted) == 1
    assert resulted[0].name == "greet"
    assert not resulted[0].is_error


async def test_tool_failure_produces_error_event(registry):
    """A tool that raises should emit ToolResulted(is_error=True), not crash the loop."""
    async def boom(**kwargs) -> str:
        raise RuntimeError("tool exploded")

    registry.register(ToolDefinition(
        name="bomb",
        description="Fails.",
        input_schema={"type": "object", "properties": {}, "required": []},
        fn=boom,
    ))

    bus, events = collect_bus()
    responses = [
        make_tool_response("bomb", "tid-bomb", {}),
        make_text_response("recovered"),
    ]
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=responses)):
        result = await loop.run("task")

    resulted = events_of(events, ToolResulted)
    assert len(resulted) == 1
    assert resulted[0].is_error
    assert "RuntimeError" in resulted[0].output
    # Loop continues — model gets the error result and responds normally
    assert result.final_text == "recovered"


# ---------------------------------------------------------------------------
# TurnEnded
# ---------------------------------------------------------------------------

async def test_turn_ended_emitted(registry):
    bus, events = collect_bus()
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(
        return_value=make_text_response("done")
    )):
        await loop.run("task")

    ended = events_of(events, TurnEnded)
    assert len(ended) == 1
    assert ended[0].turn == 1
    assert ended[0].stop_reason == "end_turn"
    assert ended[0].text == "done"


# ---------------------------------------------------------------------------
# AgentFinished
# ---------------------------------------------------------------------------

async def test_agent_finished_emitted(registry):
    bus, events = collect_bus()
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(
        return_value=make_text_response("final answer")
    )):
        await loop.run("task")

    finished = events_of(events, AgentFinished)
    assert len(finished) == 1
    assert finished[0].final_text == "final answer"
    assert finished[0].total_turns == 1


async def test_agent_finished_is_last_event(registry):
    bus, events = collect_bus()
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(
        return_value=make_text_response("ok")
    )):
        await loop.run("task")

    assert isinstance(events[-1], AgentFinished)


# ---------------------------------------------------------------------------
# AgentFailed
# ---------------------------------------------------------------------------

async def test_agent_failed_emitted_on_adapter_error(registry):
    bus, events = collect_bus()
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(
        side_effect=RuntimeError("API down")
    )):
        with pytest.raises(RuntimeError, match="API down"):
            await loop.run("task")

    failed = events_of(events, AgentFailed)
    assert len(failed) == 1
    assert failed[0].error_type == "RuntimeError"
    assert "API down" in failed[0].error
    assert failed[0].turn == 1


async def test_agent_failed_exception_is_reraised(registry):
    """AgentFailed must not swallow the exception."""
    loop = AgentLoop(registry)
    with patch.object(loop._adapter, "complete", new=AsyncMock(
        side_effect=ValueError("boom")
    )):
        with pytest.raises(ValueError, match="boom"):
            await loop.run("task")


async def test_agent_failed_not_emitted_on_success(registry):
    bus, events = collect_bus()
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(
        return_value=make_text_response("ok")
    )):
        await loop.run("task")

    assert not events_of(events, AgentFailed)


# ---------------------------------------------------------------------------
# Token accumulation
# ---------------------------------------------------------------------------

async def test_input_tokens_accumulate_across_turns(registry):
    responses = [
        make_tool_response("greet", "t1", {"name": "X"}, input_tokens=100, output_tokens=10),
        make_text_response("done", input_tokens=200, output_tokens=20),
    ]
    loop = AgentLoop(registry)
    with patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=responses)):
        result = await loop.run("task")

    assert result.total_input_tokens == 300
    assert result.total_output_tokens == 30


async def test_token_counts_match_model_responded_sum(registry):
    bus, events = collect_bus()
    responses = [
        make_tool_response("greet", "t1", {"name": "X"}, input_tokens=50, output_tokens=8),
        make_text_response("done", input_tokens=75, output_tokens=12),
    ]
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=responses)):
        result = await loop.run("task")

    responded = events_of(events, ModelResponded)
    assert sum(e.input_tokens for e in responded) == result.total_input_tokens
    assert sum(e.output_tokens for e in responded) == result.total_output_tokens


# ---------------------------------------------------------------------------
# Full event lifecycle order
# ---------------------------------------------------------------------------

async def test_event_lifecycle_order(registry):
    """Verify events arrive in the correct sequence for a tool-use turn."""
    bus, events = collect_bus()
    responses = [
        make_tool_response("greet", "t1", {"name": "X"}),
        make_text_response("done"),
    ]
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=responses)):
        await loop.run("task")

    types = [type(e).__name__ for e in events]
    # Must start with AgentStarted
    assert types[0] == "AgentStarted"
    # Must end with AgentFinished
    assert types[-1] == "AgentFinished"
    # TurnStarted before ModelCalled
    assert types.index("TurnStarted") < types.index("ModelCalled")
    # ModelCalled before ModelResponded
    assert types.index("ModelCalled") < types.index("ModelResponded")
    # ToolCalled before ToolResulted
    assert types.index("ToolCalled") < types.index("ToolResulted")
