"""Model adapter — thin wrapper around Anthropic API.

Translates harness-internal message dicts to API calls and normalizes
the response back to ModelResponse. Swap this file to change providers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import anthropic


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class AdapterConfig:
    model: str = "claude-haiku-4-5-20251001"
    max_output_tokens: int = 8096
    context_limit: int = 200_000  # tokens — all current Claude models share this limit
    system: str = "You are a helpful AI coding assistant."


# ---------------------------------------------------------------------------
# Normalized response
# ---------------------------------------------------------------------------

@dataclass
class TextBlock:
    text: str


@dataclass
class ToolUseBlock:
    tool_use_id: str
    name: str
    input: dict[str, Any]


@dataclass
class ModelResponse:
    stop_reason: str
    content: list[TextBlock | ToolUseBlock]
    input_tokens: int
    output_tokens: int
    response_id: str = ""  # Anthropic message ID (e.g. msg_01abc...)
    model_used: str = ""   # actual model string returned by API

    def text(self) -> str:
        parts = [b.text for b in self.content if isinstance(b, TextBlock)]
        return "\n".join(parts)

    def tool_uses(self) -> list[ToolUseBlock]:
        return [b for b in self.content if isinstance(b, ToolUseBlock)]


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class AnthropicAdapter:
    def __init__(self, config: AdapterConfig | None = None) -> None:
        self.config = config or AdapterConfig()
        self._client = anthropic.AsyncAnthropic()

    async def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> ModelResponse:
        kwargs: dict[str, Any] = {
            "model": self.config.model,
            "max_tokens": self.config.max_output_tokens,
            "system": self.config.system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = await self._client.messages.create(**kwargs)

        content: list[TextBlock | ToolUseBlock] = []
        for block in response.content:
            if block.type == "text":
                content.append(TextBlock(text=block.text))
            elif block.type == "tool_use":
                content.append(
                    ToolUseBlock(
                        tool_use_id=block.id,
                        name=block.name,
                        input=block.input,
                    )
                )

        return ModelResponse(
            stop_reason=response.stop_reason,
            content=content,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            response_id=response.id,
            model_used=response.model,
        )
