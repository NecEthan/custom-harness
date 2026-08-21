"""Agent execution loop — drives turn cycle, dispatches tools, emits events."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

from harness.adapter import AdapterConfig, AnthropicAdapter, ModelResponse
from harness.events import (
    AgentFailed,
    AgentFinished,
    AgentStarted,
    ContextCondensed,
    EventBus,
    ModelCalled,
    ModelResponded,
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
    context_threshold: float = 0.75  # fraction of context_limit that triggers summarization
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
        last_input_tokens = 0  # token count from the previous turn's request

        try:
            for turn in range(1, self.config.max_turns + 1):

                # Condense context if the previous turn's token usage crossed the threshold
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

                t0 = time.perf_counter()
                response: ModelResponse = await self._adapter.complete(messages, tools)
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
