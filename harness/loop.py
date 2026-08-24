"""Agent execution loop — drives turn cycle, dispatches tools, emits events."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

from harness.adapter import AdapterConfig, AnthropicAdapter, ModelResponse
from harness.errors import FailureLayer, classify
from harness.events import (
    AgentFailed,
    AgentFinished,
    AgentStarted,
    ContextCondensed,
    ControlFlowAborted,
    EventBus,
    ModelCalled,
    ModelResponded,
    RetryScheduled,
    ToolCalled,
    ToolResulted,
    TurnEnded,
    TurnStarted,
)
from harness.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Config and result
# ---------------------------------------------------------------------------

@dataclass
class LoopConfig:
    max_turns: int = 20
    context_threshold: float = 0.75      # fraction of context_limit before proactive condensation
    max_api_retries: int = 3             # max retries for transient API errors
    retry_base_delay: float = 1.0        # seconds — first retry delay
    retry_max_delay: float = 60.0        # seconds — cap on exponential backoff
    retry_backoff: float = 2.0           # multiplier per retry
    control_flow_repeat_limit: int = 3   # consecutive identical turn patterns → abort
    adapter: AdapterConfig = field(default_factory=AdapterConfig)


@dataclass
class AgentResult:
    final_text: str
    total_turns: int
    stop_reason: str
    total_input_tokens: int
    total_output_tokens: int


# ---------------------------------------------------------------------------
# Loop
# ---------------------------------------------------------------------------

class AgentLoop:
    def __init__(
        self,
        registry: ToolRegistry,
        config: LoopConfig | None = None,
        bus: EventBus | None = None,
    ) -> None:
        self.registry = registry
        self.config = config or LoopConfig()
        self.bus = bus or EventBus()
        self._adapter = AnthropicAdapter(self.config.adapter)

    async def run(self, task: str) -> AgentResult:
        await self.bus.emit(AgentStarted(task=task))

        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
        tools = self.registry.schemas()
        model = self.config.adapter.model

        total_input = 0
        total_output = 0
        final_text = ""
        stop_reason = "max_turns"
        turn = 0
        last_input_tokens = 0          # token count from the previous turn's request
        recent_turn_fingerprints: list[str] = []  # rolling window for control-flow detection

        try:
            for turn in range(1, self.config.max_turns + 1):

                # Proactive condensation: previous turn's token count crossed the threshold
                token_limit = self.config.adapter.context_limit * self.config.context_threshold
                if last_input_tokens > token_limit:
                    before = len(messages)
                    summary_response, messages = await self._condense(messages)
                    total_input += summary_response.input_tokens
                    total_output += summary_response.output_tokens
                    await self.bus.emit(ContextCondensed(
                        turn=turn,
                        messages_before=before,
                        messages_after=len(messages),
                        input_tokens_before=last_input_tokens,
                    ))

                await self.bus.emit(TurnStarted(turn=turn))

                await self.bus.emit(ModelCalled(
                    turn=turn,
                    model=model,
                    message_count=len(messages),
                    tool_count=len(tools),
                ))

                # Call the model with retry/adjust logic
                t0 = time.perf_counter()
                response, messages = await self._complete_with_recovery(messages, tools, turn)
                latency = time.perf_counter() - t0

                last_input_tokens = response.input_tokens
                total_input += response.input_tokens
                total_output += response.output_tokens

                await self.bus.emit(ModelResponded(
                    turn=turn,
                    model=model,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    latency=latency,
                    stop_reason=response.stop_reason,
                ))

                # Append assistant message
                messages.append({"role": "assistant", "content": self._response_to_content(response)})

                final_text = response.text()
                await self.bus.emit(TurnEnded(
                    turn=turn,
                    stop_reason=response.stop_reason,
                    text=final_text,
                ))

                if response.stop_reason != "tool_use" or not response.tool_uses():
                    stop_reason = response.stop_reason
                    break

                # Control-flow detection: fingerprint this turn's tool calls
                turn_fp = "|".join(sorted(
                    f"{tu.name}:{json.dumps(tu.input, sort_keys=True)}"
                    for tu in response.tool_uses()
                ))
                recent_turn_fingerprints.append(turn_fp)
                if len(recent_turn_fingerprints) > self.config.control_flow_repeat_limit:
                    recent_turn_fingerprints.pop(0)

                if (
                    len(recent_turn_fingerprints) == self.config.control_flow_repeat_limit
                    and len(set(recent_turn_fingerprints)) == 1
                ):
                    await self.bus.emit(ControlFlowAborted(
                        turn=turn,
                        repeated_count=self.config.control_flow_repeat_limit,
                        fingerprint=turn_fp,
                    ))
                    stop_reason = "control_flow"
                    break

                # Dispatch all tool calls, collect results
                tool_results: list[dict[str, Any]] = []
                for tool_use in response.tool_uses():
                    await self.bus.emit(ToolCalled(
                        turn=turn,
                        tool_use_id=tool_use.tool_use_id,
                        name=tool_use.name,
                        input=tool_use.input,
                    ))

                    t_tool = time.perf_counter()
                    result = await self.registry.call(
                        name=tool_use.name,
                        tool_use_id=tool_use.tool_use_id,
                        input_dict=tool_use.input,
                    )
                    tool_duration = time.perf_counter() - t_tool

                    await self.bus.emit(ToolResulted(
                        turn=turn,
                        tool_use_id=tool_use.tool_use_id,
                        name=tool_use.name,
                        output=result.output,
                        is_error=result.is_error,
                        duration=tool_duration,
                    ))

                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": result.tool_use_id,
                        "content": result.output,
                        **({"is_error": True} if result.is_error else {}),
                    })

                messages.append({"role": "user", "content": tool_results})

        except Exception as exc:
            await self.bus.emit(AgentFailed(
                turn=turn or None,
                error=str(exc),
                error_type=type(exc).__name__,
            ))
            raise

        await self.bus.emit(AgentFinished(
            total_turns=turn,
            final_text=final_text,
        ))

        return AgentResult(
            final_text=final_text,
            total_turns=turn,
            stop_reason=stop_reason,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
        )

    async def _complete_with_recovery(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        turn: int,
    ) -> tuple[ModelResponse, list[dict[str, Any]]]:
        """Call adapter.complete() with retry for API errors and inline condensation for context errors.

        Returns (response, messages) — messages may differ from input if context was condensed.
        """
        api_attempts = 0
        context_adjusted = False

        while True:
            try:
                response = await self._adapter.complete(messages, tools)
                return response, messages

            except Exception as exc:
                layer = classify(exc)

                # Transient API error — retry with exponential backoff
                if layer == FailureLayer.API and api_attempts < self.config.max_api_retries:
                    api_attempts += 1
                    delay = min(
                        self.config.retry_base_delay * (self.config.retry_backoff ** (api_attempts - 1)),
                        self.config.retry_max_delay,
                    )
                    await self.bus.emit(RetryScheduled(
                        turn=turn,
                        attempt=api_attempts,
                        error=str(exc),
                        error_type=type(exc).__name__,
                        delay=delay,
                        layer=layer.value,
                    ))
                    await asyncio.sleep(delay)
                    continue

                # Context overflow — condense and retry once
                if layer == FailureLayer.CONTEXT and not context_adjusted:
                    context_adjusted = True
                    before = len(messages)
                    _, messages = await self._condense(messages)
                    await self.bus.emit(ContextCondensed(
                        turn=turn,
                        messages_before=before,
                        messages_after=len(messages),
                        input_tokens_before=0,  # unknown — the call failed before returning usage
                    ))
                    continue

                raise  # FATAL, or retries/adjustments exhausted

    async def _condense(
        self, messages: list[dict[str, Any]]
    ) -> tuple[ModelResponse, list[dict[str, Any]]]:
        """Summarize conversation history and return a condensed messages list.

        Keeps the original user task and the last 4 messages (2 turn pairs) verbatim.
        Everything in between is replaced with a model-generated summary.
        """
        history_text = self._messages_to_text(messages)
        summary_response = await self._adapter.complete(
            messages=[{
                "role": "user",
                "content": (
                    "Summarize the following agent conversation concisely. "
                    "Preserve: the original task, key decisions, tool calls and their results, "
                    "current progress, and any important state. Be specific about what was "
                    "done and what still needs to be done.\n\n"
                    + history_text
                ),
            }],
            tools=None,
        )
        summary = summary_response.text()

        # Keep original task + summary bridge + last 4 messages for immediate context
        tail_start = max(1, len(messages) - 4)
        condensed: list[dict[str, Any]] = [
            messages[0],  # original user task — never drop
            {"role": "assistant", "content": [{"type": "text", "text": f"[Summary of prior work: {summary}]"}]},
            {"role": "user", "content": "Continue with the task based on the summary above."},
            *messages[tail_start:],
        ]
        return summary_response, condensed

    @staticmethod
    def _messages_to_text(messages: list[dict[str, Any]]) -> str:
        """Render messages list as plain text for the summarization prompt."""
        parts = []
        for msg in messages:
            role = msg["role"].upper()
            content = msg["content"]
            if isinstance(content, str):
                parts.append(f"{role}: {content}")
            elif isinstance(content, list):
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    btype = block.get("type", "")
                    if btype == "text":
                        parts.append(f"{role}: {block['text']}")
                    elif btype == "tool_use":
                        parts.append(f"{role} [tool:{block['name']}]: {json.dumps(block.get('input', {}))}")
                    elif btype == "tool_result":
                        parts.append(f"{role} [result:{block.get('tool_use_id', '')}]: {block.get('content', '')}")
        return "\n\n".join(parts)

    @staticmethod
    def _response_to_content(response: ModelResponse) -> list[dict[str, Any]]:
        """Convert normalized ModelResponse content back to Anthropic API content blocks."""
        from harness.adapter import TextBlock, ToolUseBlock
        blocks = []
        for block in response.content:
            if isinstance(block, TextBlock):
                blocks.append({"type": "text", "text": block.text})
            elif isinstance(block, ToolUseBlock):
                blocks.append({
                    "type": "tool_use",
                    "id": block.tool_use_id,
                    "name": block.name,
                    "input": block.input,
                })
        return blocks
