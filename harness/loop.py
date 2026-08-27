"""Agent execution loop — drives turn cycle, dispatches tools, emits events."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from harness.memory import MemoryManager

from harness.adapter import AdapterConfig, AnthropicAdapter, ModelResponse, TextBlock, ToolUseBlock
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
from harness.recovery import complete_with_recovery, condense
from harness.registry import ToolRegistry


# ---------------------------------------------------------------------------
# Config and result
# ---------------------------------------------------------------------------

@dataclass
class LoopConfig:
    max_turns: int = 20
    context_threshold: float = 0.75
    max_api_retries: int = 3
    retry_base_delay: float = 1.0
    retry_max_delay: float = 60.0
    retry_backoff: float = 2.0
    control_flow_repeat_limit: int = 3
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
        memory: "MemoryManager | None" = None,
    ) -> None:
        self.registry = registry
        self.config = config or LoopConfig()
        self.bus = bus or EventBus()
        self._adapter = AnthropicAdapter(self.config.adapter)
        self.memory = memory

    async def run(self, task: str) -> AgentResult:
        await self.bus.emit(AgentStarted(task=task))

        messages: list[dict[str, Any]] = [{"role": "user", "content": task}]
        if self.memory:
            messages = await self.memory.before_run(task, messages)

        tools = self.registry.schemas()
        model = self.config.adapter.model
        total_input = total_output = 0
        final_text = ""
        stop_reason = "max_turns"
        turn = 0
        last_input_tokens = 0
        recent_fingerprints: list[str] = []

        try:
            for turn in range(1, self.config.max_turns + 1):

                # Proactive condensation when approaching context limit
                if last_input_tokens > self.config.adapter.context_limit * self.config.context_threshold:
                    before = len(messages)
                    summary_resp, messages = await condense(self._adapter, messages)
                    total_input += summary_resp.input_tokens
                    total_output += summary_resp.output_tokens
                    await self.bus.emit(ContextCondensed(
                        turn=turn,
                        messages_before=before,
                        messages_after=len(messages),
                        input_tokens_before=last_input_tokens,
                    ))

                await self.bus.emit(TurnStarted(turn=turn))
                await self.bus.emit(ModelCalled(
                    turn=turn, model=model,
                    message_count=len(messages), tool_count=len(tools),
                ))

                t0 = time.perf_counter()
                response, messages = await complete_with_recovery(
                    self._adapter, self.config, self.bus, messages, tools, turn
                )
                latency = time.perf_counter() - t0

                last_input_tokens = response.input_tokens
                total_input += response.input_tokens
                total_output += response.output_tokens

                await self.bus.emit(ModelResponded(
                    turn=turn, model=model,
                    input_tokens=response.input_tokens,
                    output_tokens=response.output_tokens,
                    latency=latency,
                    stop_reason=response.stop_reason,
                ))

                messages.append({"role": "assistant", "content": _response_to_content(response)})
                final_text = response.text()
                await self.bus.emit(TurnEnded(
                    turn=turn, stop_reason=response.stop_reason, text=final_text,
                ))

                if response.stop_reason != "tool_use" or not response.tool_uses():
                    stop_reason = response.stop_reason
                    break

                # Control-flow loop detection
                fp = "|".join(sorted(
                    f"{tu.name}:{json.dumps(tu.input, sort_keys=True)}"
                    for tu in response.tool_uses()
                ))
                recent_fingerprints = (recent_fingerprints + [fp])[-self.config.control_flow_repeat_limit:]
                if (
                    len(recent_fingerprints) == self.config.control_flow_repeat_limit
                    and len(set(recent_fingerprints)) == 1
                ):
                    await self.bus.emit(ControlFlowAborted(
                        turn=turn,
                        repeated_count=self.config.control_flow_repeat_limit,
                        fingerprint=fp,
                    ))
                    stop_reason = "control_flow"
                    break

                # Dispatch tool calls
                tool_results: list[dict[str, Any]] = []
                for tu in response.tool_uses():
                    await self.bus.emit(ToolCalled(
                        turn=turn, tool_use_id=tu.tool_use_id, name=tu.name, input=tu.input,
                    ))
                    t_tool = time.perf_counter()
                    result = await self.registry.call(
                        name=tu.name, tool_use_id=tu.tool_use_id, input_dict=tu.input,
                    )
                    await self.bus.emit(ToolResulted(
                        turn=turn, tool_use_id=tu.tool_use_id, name=tu.name,
                        output=result.output, is_error=result.is_error,
                        duration=time.perf_counter() - t_tool,
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
                turn=turn or None, error=str(exc), error_type=type(exc).__name__,
            ))
            raise

        await self.bus.emit(AgentFinished(total_turns=turn, final_text=final_text))

        if self.memory:
            try:
                await self.memory.after_run(task, messages)
            except Exception:
                pass

        return AgentResult(
            final_text=final_text,
            total_turns=turn,
            stop_reason=stop_reason,
            total_input_tokens=total_input,
            total_output_tokens=total_output,
        )


def _response_to_content(response: ModelResponse) -> list[dict[str, Any]]:
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
