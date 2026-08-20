"""Tests for AgentLoop — adapter mocked, no real API calls."""

import pytest
from unittest.mock import AsyncMock, patch

from harness.adapter import ModelResponse, TextBlock, ToolUseBlock
from harness.events import AgentFinished, EventBus, ToolCalled, ToolResulted, TurnEnded, TurnStarted
from harness.loop import AgentLoop, LoopConfig
from harness.registry import ToolDefinition, ToolRegistry


def make_text_response(text: str) -> ModelResponse:
    return ModelResponse(
        stop_reason="end_turn",
        content=[TextBlock(text=text)],
        input_tokens=10,
        output_tokens=5,
    )


def make_tool_response(name: str, tool_id: str, input_dict: dict) -> ModelResponse:
    return ModelResponse(
        stop_reason="tool_use",
        content=[ToolUseBlock(tool_use_id=tool_id, name=name, input=input_dict)],
        input_tokens=20,
        output_tokens=10,
    )


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


async def test_events_emitted(registry):
    events = []

    async def collect(event):
        events.append(event)

    bus = EventBus()
    bus.subscribe(collect)

    responses = [
        make_tool_response("greet", "tid-2", {"name": "Eve"}),
        make_text_response("Hi Eve."),
    ]
    loop = AgentLoop(registry, bus=bus)
    with patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=responses)):
        await loop.run("Greet Eve.")

    types = [type(e) for e in events]
    assert TurnStarted in types
    assert ToolCalled in types
    assert ToolResulted in types
    assert TurnEnded in types
    assert AgentFinished in types
