"""Retry and context-condensation helpers for AgentLoop.

Extracted here to keep loop.py focused on the turn cycle.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from harness.adapter import AnthropicAdapter, ModelResponse
from harness.errors import FailureLayer, classify
from harness.events import ContextCondensed, EventBus, RetryScheduled

if TYPE_CHECKING:
    from harness.loop import LoopConfig


async def complete_with_recovery(
    adapter: AnthropicAdapter,
    config: "LoopConfig",
    bus: EventBus,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    turn: int,
) -> tuple[ModelResponse, list[dict[str, Any]]]:
    """Call adapter.complete() with retry for API errors and inline condensation for context errors.

    Returns (response, messages) — messages may differ if context was condensed.
    """
    api_attempts = 0
    context_adjusted = False

    while True:
        try:
            return await adapter.complete(messages, tools), messages

        except Exception as exc:
            layer = classify(exc)

            if layer == FailureLayer.API and api_attempts < config.max_api_retries:
                api_attempts += 1
                delay = min(
                    config.retry_base_delay * (config.retry_backoff ** (api_attempts - 1)),
                    config.retry_max_delay,
                )
                await bus.emit(RetryScheduled(
                    turn=turn,
                    attempt=api_attempts,
                    error=str(exc),
                    error_type=type(exc).__name__,
                    delay=delay,
                    layer=layer.value,
                ))
                await asyncio.sleep(delay)
                continue

            if layer == FailureLayer.CONTEXT and not context_adjusted:
                context_adjusted = True
                before = len(messages)
                _, messages = await condense(adapter, messages)
                await bus.emit(ContextCondensed(
                    turn=turn,
                    messages_before=before,
                    messages_after=len(messages),
                    input_tokens_before=0,
                ))
                continue

            raise


async def condense(
    adapter: AnthropicAdapter,
    messages: list[dict[str, Any]],
) -> tuple[ModelResponse, list[dict[str, Any]]]:
    """Summarize conversation history and return a condensed messages list.

    Keeps the original user task and the last 4 messages verbatim.
    """
    history_text = _messages_to_text(messages)
    summary_response = await adapter.complete(
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

    tail_start = max(1, len(messages) - 4)
    condensed: list[dict[str, Any]] = [
        messages[0],
        {"role": "assistant", "content": [{"type": "text", "text": f"[Summary of prior work: {summary}]"}]},
        {"role": "user", "content": "Continue with the task based on the summary above."},
        *messages[tail_start:],
    ]
    return summary_response, condensed


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
