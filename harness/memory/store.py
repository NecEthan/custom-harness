"""Filesystem-backed memory store — one .md file per entry.

File format
-----------
---
id: a1b2c3d4
title: User prefers pytest fixtures over class-based tests
tags: testing,preferences
created: 2026-08-24T10:00:00+00:00
last_used: 2026-08-24T10:00:00+00:00
importance: 0.7
---

Body text here.
"""

from __future__ import annotations

import re
from pathlib import Path

from .types import Memory


# ---------------------------------------------------------------------------
# Serialise / parse
# ---------------------------------------------------------------------------

def _serialize(m: Memory) -> str:
    return (
        "---\n"
        f"id: {m.id}\n"
        f"title: {m.title}\n"
        f"tags: {','.join(m.tags)}\n"
        f"created: {m.created}\n"
        f"last_used: {m.last_used}\n"
        f"importance: {m.importance}\n"
        "---\n\n"
        f"{m.body}\n"
    )


def _parse(text: str) -> Memory | None:
    match = re.match(r"^---\n(.*?)\n---\n+(.*)", text, re.DOTALL)
    if not match:
        return None
    meta_text, body = match.group(1), match.group(2).strip()

    meta: dict[str, str] = {}
    for line in meta_text.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            meta[k.strip()] = v.strip()

    tags_raw = meta.get("tags", "")
    tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

    try:
        importance = float(meta.get("importance", "0.5"))
    except ValueError:
        importance = 0.5

    return Memory(
        id=meta.get("id", ""),
        title=meta.get("title", ""),
        body=body,
        tags=tags,
        created=meta.get("created", ""),
        last_used=meta.get("last_used", ""),
        importance=importance,
    )


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------

class MemoryStore:
    """CRUD over a directory of .md memory files."""

    def __init__(self, path: str | Path) -> None:
        self.root = Path(path)
        self.root.mkdir(parents=True, exist_ok=True)

    def list(self) -> list[Memory]:
        memories: list[Memory] = []
        for f in sorted(self.root.glob("*.md")):
            m = _parse(f.read_text(encoding="utf-8"))
            if m:
                memories.append(m)
        return memories

    def get(self, id: str) -> Memory | None:
        path = self.root / f"{id}.md"
        if not path.exists():
            return None
        return _parse(path.read_text(encoding="utf-8"))

    def save(self, memory: Memory) -> None:
        path = self.root / f"{memory.id}.md"
        path.write_text(_serialize(memory), encoding="utf-8")

    def delete(self, id: str) -> None:
        path = self.root / f"{id}.md"
        if path.exists():
            path.unlink()

    def clear(self) -> None:
        for f in self.root.glob("*.md"):
            f.unlink()
