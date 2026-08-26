"""Extraction — end-of-run pass that identifies and persists new memories."""

from __future__ import annotations

import json
from typing import Any

from harness.adapter import AnthropicAdapter

from .store import MemoryStore
from .types import Memory

_PROMPT = """\
Review this agent conversation and extract facts worth keeping as long-term memory.

SAVE:
- User preferences and workflow habits
- Architectural decisions and their rationale
- Non-obvious patterns discovered in the codebase
- Accumulated context that took real effort to learn

DO NOT SAVE:
- Facts readable directly from project files (README, config, source)
- Things findable in < 5 seconds with grep or git log
- Task-specific one-off details with no future value

Return a JSON array. Each element:
  {{"title": "short title", "body": "concise description", "tags": ["tag1"], "importance": 0.0-1.0}}

If nothing is worth saving, return [].
Return ONLY the JSON array — no preamble, no markdown fence.

Conversation:
{conversation}
"""


def _messages_to_text(messages: list[dict[str, Any]]) -> str:
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
                    parts.append(
                        f"{role} [tool:{block['name']}]: {json.dumps(block.get('input', {}))}"
                    )
                elif btype == "tool_result":
                    parts.append(
                        f"{role} [result:{block.get('tool_use_id', '')}]: {block.get('content', '')}"
                    )
    return "\n\n".join(parts)


class MemoryExtractor:
    """Identify memorable facts from a completed run and write them to the store."""

    def __init__(self, store: MemoryStore, adapter: AnthropicAdapter) -> None:
        self.store = store
        self._adapter = adapter

    async def extract(
        self,
        task: str,  # noqa: ARG002 — reserved for future task-aware filtering
        messages: list[dict[str, Any]],
    ) -> list[Memory]:
        conversation = _messages_to_text(messages)
        response = await self._adapter.complete(
            messages=[{
                "role": "user",
                "content": _PROMPT.format(conversation=conversation),
            }],
            tools=None,
        )

        try:
            items = json.loads(response.text())
        except Exception:
            return []

        if not isinstance(items, list):
            return []

        saved: list[Memory] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            body = str(item.get("body", "")).strip()
            if not title or not body:
                continue
            tags_raw = item.get("tags", [])
            tags = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []
            importance = float(item.get("importance", 0.5))
            m = Memory(title=title, body=body, tags=tags, importance=importance)
            self.store.save(m)
            saved.append(m)

        return saved
