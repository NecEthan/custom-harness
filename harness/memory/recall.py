"""Recall — query-time injection of relevant memories into the message list."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from harness.adapter import AnthropicAdapter

from .store import MemoryStore
from .types import Memory


class MemoryRecall:
    """Rank stored memories by relevance to the current task and inject them."""

    def __init__(
        self,
        store: MemoryStore,
        adapter: AnthropicAdapter,
        top_k: int = 5,
    ) -> None:
        self.store = store
        self._adapter = adapter
        self.top_k = top_k

    async def inject(
        self,
        task: str,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Return messages with a <memory> block prepended to messages[0].

        If the store is empty, or no memories are relevant, returns messages unchanged.
        """
        memories = self.store.list()
        if not memories:
            return messages

        selected = await self._rank(task, memories)
        if not selected:
            return messages

        # Update last_used on selected entries
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for m in selected:
            m.last_used = now
            self.store.save(m)

        block = _format_block(selected)
        messages = list(messages)  # shallow copy — do not mutate caller's list
        first = messages[0]
        content = first["content"]
        if isinstance(content, str):
            messages[0] = {**first, "content": block + content}
        else:
            messages[0] = {**first, "content": [{"type": "text", "text": block}, *list(content)]}
        return messages

    async def _rank(self, task: str, memories: list[Memory]) -> list[Memory]:
        """If few memories, return all; otherwise ask the model to pick the top_k."""
        if len(memories) <= self.top_k:
            return memories

        index = "\n".join(
            f"- id:{m.id}  title:{m.title}  tags:{','.join(m.tags)}"
            for m in memories
        )
        response = await self._adapter.complete(
            messages=[{
                "role": "user",
                "content": (
                    f"Task: {task}\n\n"
                    f"Available memories:\n{index}\n\n"
                    f"Return a JSON array of up to {self.top_k} memory IDs most relevant "
                    f"to this task, most relevant first. "
                    f'Example: ["a1b2c3d4", "e5f6g7h8"]. '
                    f"Return only the JSON array, no other text."
                ),
            }],
            tools=None,
        )

        try:
            ids: list[str] = json.loads(response.text())
            id_to_mem = {m.id: m for m in memories}
            return [id_to_mem[i] for i in ids if i in id_to_mem][: self.top_k]
        except Exception:
            return memories[: self.top_k]  # fallback: first N by file order


def _format_block(memories: list[Memory]) -> str:
    parts = ["<memory>"]
    for m in memories:
        parts.append(f"### [{m.id}] {m.title}")
        parts.append(m.body)
    parts.append("</memory>\n")
    return "\n\n".join(parts) + "\n"
