"""Tests for error recovery — API retries, context overflow recovery, control-flow abort."""

from __future__ import annotations

import httpx
import pytest
from unittest.mock import AsyncMock, patch

import anthropic

from harness.adapter import AdapterConfig, ModelResponse, TextBlock, ToolUseBlock
from harness.errors import FailureLayer, classify
from harness.events import (
    AgentFailed,
    AgentFinished,
    ContextCondensed,
    ControlFlowAborted,
    EventBus,
    RetryScheduled,
)
from harness.loop import AgentLoop, LoopConfig
from harness.registry import ToolDefinition, ToolRegistry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_text_response(text: str = "done", input_tokens: int = 10, output_tokens: int = 5) -> ModelResponse:
    return ModelResponse(
        stop_reason="end_turn",
        content=[TextBlock(text=text)],
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )


def make_tool_response(name: str, tool_id: str, input_dict: dict, input_tokens: int = 20) -> ModelResponse:
    return ModelResponse(
        stop_reason="tool_use",
        content=[ToolUseBlock(tool_use_id=tool_id, name=name, input=input_dict)],
        input_tokens=input_tokens,
        output_tokens=10,
    )


def collect_bus() -> tuple[EventBus, list]:
    events = []

    async def collect(event):
        events.append(event)

    bus = EventBus()
    bus.subscribe(collect)
    return bus, events


def events_of(events: list, cls) -> list:
    return [e for e in events if isinstance(e, cls)]


def _response(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "https://api.anthropic.com/v1/messages"))


def make_rate_limit_error() -> anthropic.RateLimitError:
    return anthropic.RateLimitError(
        message="rate limit exceeded",
        response=_response(429),
        body=None,
    )


def make_overload_error() -> anthropic.InternalServerError:
    return anthropic.InternalServerError(
        message="overloaded",
        response=_response(529),
        body=None,
    )


def make_context_overflow_error() -> anthropic.BadRequestError:
    return anthropic.BadRequestError(
        message="prompt is too long: 210000 tokens > 200000 maximum",
        response=_response(400),
        body=None,
    )


def make_fatal_error() -> anthropic.BadRequestError:
    return anthropic.BadRequestError(
        message="invalid request: bad schema",
        response=_response(400),
        body=None,
    )


@pytest.fixture
def registry():
    r = ToolRegistry()
    r.register(ToolDefinition(
        name="noop",
        description="Does nothing.",
        input_schema={"type": "object", "properties": {}, "required": []},
        fn=AsyncMock(return_value="ok"),
    ))
    return r


# ---------------------------------------------------------------------------
# Error classification
# ---------------------------------------------------------------------------

def test_rate_limit_is_api_layer():
    assert classify(make_rate_limit_error()) == FailureLayer.API


def test_overload_is_api_layer():
    assert classify(make_overload_error()) == FailureLayer.API


def test_timeout_is_api_layer():
    assert classify(anthropic.APITimeoutError(request=httpx.Request("POST", "https://api.anthropic.com"))) == FailureLayer.API


def test_context_overflow_is_context_layer():
    assert classify(make_context_overflow_error()) == FailureLayer.CONTEXT


def test_bad_schema_is_fatal():
    assert classify(make_fatal_error()) == FailureLayer.FATAL


def test_unknown_exception_is_fatal():
    assert classify(RuntimeError("something else")) == FailureLayer.FATAL


# ---------------------------------------------------------------------------
# API layer: retry with backoff
# ---------------------------------------------------------------------------

async def test_api_error_retried_then_succeeds(registry):
    bus, events = collect_bus()
    config = LoopConfig(max_api_retries=2, retry_base_delay=0, retry_backoff=1)
    loop = AgentLoop(registry, config=config, bus=bus)

    side_effects = [make_rate_limit_error(), make_rate_limit_error(), make_text_response("ok")]
    with (
        patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=side_effects)),
        patch("harness.recovery.asyncio.sleep", new=AsyncMock()),
    ):
        result = await loop.run("task")

    assert result.final_text == "ok"
    retries = events_of(events, RetryScheduled)
    assert len(retries) == 2
    assert retries[0].attempt == 1
    assert retries[1].attempt == 2
    assert retries[0].layer == "api"


async def test_api_error_exhausts_retries_and_raises(registry):
    bus, events = collect_bus()
    config = LoopConfig(max_api_retries=2, retry_base_delay=0, retry_backoff=1)
    loop = AgentLoop(registry, config=config, bus=bus)

    side_effects = [make_rate_limit_error()] * 3  # one more than max_api_retries
    with (
        patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=side_effects)),
        patch("harness.recovery.asyncio.sleep", new=AsyncMock()),
        pytest.raises(anthropic.RateLimitError),
    ):
        await loop.run("task")

    retries = events_of(events, RetryScheduled)
    assert len(retries) == 2  # retried max_api_retries times, then gave up
    assert events_of(events, AgentFailed)


async def test_retry_delay_is_exponential(registry):
    config = LoopConfig(max_api_retries=3, retry_base_delay=2.0, retry_backoff=3.0, retry_max_delay=1000)
    loop = AgentLoop(registry, config=config)

    side_effects = [make_rate_limit_error(), make_rate_limit_error(), make_rate_limit_error(), make_text_response()]
    sleep_calls = []

    async def record_sleep(delay):
        sleep_calls.append(delay)

    with (
        patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=side_effects)),
        patch("harness.recovery.asyncio.sleep", new=record_sleep),
    ):
        await loop.run("task")

    # delays: 2.0*3^0=2, 2.0*3^1=6, 2.0*3^2=18
    assert sleep_calls == [2.0, 6.0, 18.0]


async def test_retry_delay_capped_at_max(registry):
    config = LoopConfig(max_api_retries=3, retry_base_delay=100.0, retry_backoff=10.0, retry_max_delay=60.0)
    loop = AgentLoop(registry, config=config)

    side_effects = [make_rate_limit_error(), make_rate_limit_error(), make_text_response()]
    sleep_calls = []

    async def record_sleep(delay):
        sleep_calls.append(delay)

    with (
        patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=side_effects)),
        patch("harness.recovery.asyncio.sleep", new=record_sleep),
    ):
        await loop.run("task")

    assert all(d <= 60.0 for d in sleep_calls)


async def test_fatal_error_not_retried(registry):
    bus, events = collect_bus()
    config = LoopConfig(max_api_retries=3, retry_base_delay=0)
    loop = AgentLoop(registry, config=config, bus=bus)

    with (
        patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=make_fatal_error())),
        patch("harness.recovery.asyncio.sleep", new=AsyncMock()),
        pytest.raises(anthropic.BadRequestError),
    ):
        await loop.run("task")

    assert not events_of(events, RetryScheduled)  # no retries for fatal errors
    assert events_of(events, AgentFailed)


# ---------------------------------------------------------------------------
# Context layer: reactive condensation
# ---------------------------------------------------------------------------

async def test_context_overflow_triggers_inline_condensation(registry):
    bus, events = collect_bus()
    loop = AgentLoop(registry, bus=bus)

    summary_resp = make_text_response("summary", input_tokens=5)
    final = make_text_response("done")

    # First call overflows, then summary call, then retry succeeds
    side_effects = [make_context_overflow_error(), summary_resp, final]
    with patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=side_effects)):
        result = await loop.run("task")

    condensed = events_of(events, ContextCondensed)
    assert len(condensed) == 1
    assert condensed[0].input_tokens_before == 0  # unknown at time of reactive condensation
    assert result.final_text == "done"


async def test_context_overflow_only_adjusted_once(registry):
    """If condensation doesn't help (still overflows), the error is re-raised."""
    loop = AgentLoop(registry)

    # First call: overflow. Second call (summary): ok. Third call (retry): overflow again.
    summary_resp = make_text_response("summary", input_tokens=5)
    side_effects = [make_context_overflow_error(), summary_resp, make_context_overflow_error()]

    with (
        patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=side_effects)),
        pytest.raises(anthropic.BadRequestError),
    ):
        await loop.run("task")


# ---------------------------------------------------------------------------
# Control flow: repeated tool calls
# ---------------------------------------------------------------------------

async def test_control_flow_abort_on_repeated_turns(registry):
    bus, events = collect_bus()
    config = LoopConfig(control_flow_repeat_limit=3, max_turns=20)
    loop = AgentLoop(registry, config=config, bus=bus)

    # Same tool call every turn
    repeated = make_tool_response("noop", "t1", {})

    with patch.object(loop._adapter, "complete", new=AsyncMock(return_value=repeated)):
        result = await loop.run("task")

    aborted = events_of(events, ControlFlowAborted)
    assert len(aborted) == 1
    assert aborted[0].repeated_count == 3
    assert result.stop_reason == "control_flow"


async def test_control_flow_not_triggered_for_varied_calls(registry):
    bus, events = collect_bus()
    config = LoopConfig(control_flow_repeat_limit=3, max_turns=20)
    loop = AgentLoop(registry, config=config, bus=bus)

    # Different tool inputs each turn
    responses = [
        make_tool_response("noop", f"t{i}", {"n": i})
        for i in range(5)
    ] + [make_text_response("done")]

    with patch.object(loop._adapter, "complete", new=AsyncMock(side_effect=responses)):
        result = await loop.run("task")

    assert not events_of(events, ControlFlowAborted)
    assert result.stop_reason == "end_turn"


async def test_control_flow_abort_emitted_before_agent_finished(registry):
    bus, events = collect_bus()
    config = LoopConfig(control_flow_repeat_limit=2)
    loop = AgentLoop(registry, config=config, bus=bus)

    repeated = make_tool_response("noop", "t1", {})
    with patch.object(loop._adapter, "complete", new=AsyncMock(return_value=repeated)):
        await loop.run("task")

    types = [type(e).__name__ for e in events]
    assert "ControlFlowAborted" in types
    assert types.index("ControlFlowAborted") < types.index("AgentFinished")
