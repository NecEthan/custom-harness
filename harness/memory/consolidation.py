"""Consolidation — rare maintenance pass to merge duplicates and prune stale entries."""

from __future__ import annotations

import json

from harness.adapter import AnthropicAdapter

from .store import MemoryStore
from .types import Memory

_PROMPT = """\
Review these memory entries and produce a consolidated list.

Rules:
1. Merge duplicate or highly similar entries into one
2. Remove stale, trivial, or easily re-derived entries
3. Sharpen the wording of kept entries

Memories:
{memories_text}

Return a JSON array of the consolidated memories. Each element:
  {{"id": "keep_if_unchanged", "title": "...", "body": "...", "tags": [...], "importance": 0.0-1.0}}

Include "id" only when preserving an existing entry without merging.
Return ONLY the JSON array — no preamble, no markdown fence.
"""


class MemoryConsolidator:
    """Merge duplicates and prune stale memories.  Run infrequently (e.g. every N runs)."""

    def __init__(self, store: MemoryStore, adapter: AnthropicAdapter) -> None:
        self.store = store
        self._adapter = adapter

    async def consolidate(self) -> int:
        """Rewrite the store with a consolidated set.  Returns number of entries removed."""
        memories = self.store.list()
        if len(memories) < 2:
            return 0

        memories_text = "\n\n---\n\n".join(
            f"id: {m.id}\ntitle: {m.title}\ntags: {','.join(m.tags)}\n"
            f"importance: {m.importance}\n\n{m.body}"
            for m in memories
        )

        response = await self._adapter.complete(
            messages=[{
                "role": "user",
                "content": _PROMPT.format(memories_text=memories_text),
            }],
            tools=None,
        )

        try:
            items = json.loads(response.text())
        except Exception:
            return 0

        if not isinstance(items, list):
            return 0

        old_by_id = {m.id: m for m in memories}
        new_memories: list[Memory] = []

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
            existing_id = str(item.get("id", ""))

            if existing_id and existing_id in old_by_id:
                old = old_by_id[existing_id]
                new_memories.append(Memory(
                    id=old.id,
                    title=title,
                    body=body,
                    tags=tags,
                    importance=importance,
                    created=old.created,
                    last_used=old.last_used,
                ))
            else:
                new_memories.append(Memory(title=title, body=body, tags=tags, importance=importance))

        removed = len(memories) - len(new_memories)
        self.store.clear()
        for m in new_memories:
            self.store.save(m)
        return removed
