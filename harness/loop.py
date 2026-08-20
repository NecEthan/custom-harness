"""Agent execution loop — drives turn cycle, dispatches tools, emits events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from harness.adapter import AdapterConfig, AnthropicAdapter, ModelResponse
from harness.events import (
    AgentFinished,
    EventBus,
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
        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
        tools = self.registry.schemas()

        total_input = 0
        total_output = 0
        final_text = ""
        stop_reason = "max_turns"

        for turn in range(1, self.config.max_turns + 1):
            await self.bus.emit(TurnStarted(turn=turn))

            response: ModelResponse = await self._adapter.complete(messages, tools)
            total_input += response.input_tokens
            total_output += response.output_tokens

            # Append assistant message
            messages.append({"role": "assistant", "content": self._response_to_content(response)})

            final_text = response.text
            await self.bus.emit(TurnEnded(
                turn=turn,
                stop_reason=response.stop_reason,
                text=final_text,
            ))

            if response.stop_reason != "tool_use" or not response.tool_uses:
                stop_reason = response.stop_reason
                break

            # Dispatch all tool calls, collect results
            tool_results: list[dict[str, Any]] = []
            for tool_use in response.tool_uses:
                await self.bus.emit(ToolCalled(
                    turn=turn,
                    tool_use_id=tool_use.tool_use_id,
                    name=tool_use.name,
                    input=tool_use.input,
                ))

                result = await self.registry.call(
                    name=tool_use.name,
                    tool_use_id=tool_use.tool_use_id,
                    input_dict=tool_use.input,
                )

                await self.bus.emit(ToolResulted(
                    turn=turn,
                    tool_use_id=tool_use.tool_use_id,
                    name=tool_use.name,
                    output=result.output,
                    is_error=result.is_error,
                ))

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": result.tool_use_id,
                    "content": result.output,
                    **({"is_error": True} if result.is_error else {}),
                })

            messages.append({"role": "user", "content": tool_results})

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
