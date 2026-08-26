"""Agent memory subsystem.

Four operations
---------------
Selection   Decides what is worth saving.  Baked into the extraction prompt.
Recall      Runs at query time: ranks stored memories, injects relevant ones
            as a <memory> block ahead of messages[0].
Extraction  Runs at run end: LLM identifies new memorable facts, writes .md files.
Consolidation
            Runs rarely: merges duplicates, prunes stale entries.

Typical usage
-------------
    from harness.memory import MemoryManager, MemoryStore

    store   = MemoryStore("memory/")
    manager = MemoryManager(store)

    # Before a run:
    messages = await manager.before_run(task, messages)

    # After a run:
    await manager.after_run(task, messages)

    # Occasionally:
    removed = await manager.consolidate()
"""

from __future__ import annotations

from typing import Any

from harness.adapter import AdapterConfig, AnthropicAdapter

from .consolidation import MemoryConsolidator
from .extraction import MemoryExtractor
from .recall import MemoryRecall
from .store import MemoryStore
from .types import Memory

__all__ = [
    "Memory",
    "MemoryStore",
    "MemoryManager",
    "MemoryRecall",
    "MemoryExtractor",
    "MemoryConsolidator",
]


class MemoryManager:
    """Orchestrates Recall, Extraction, and Consolidation over a MemoryStore."""

    def __init__(
        self,
        store: MemoryStore,
        adapter: AnthropicAdapter | None = None,
        adapter_config: AdapterConfig | None = None,
        top_k: int = 5,
    ) -> None:
        if adapter is None:
            adapter = AnthropicAdapter(adapter_config or AdapterConfig())
        self._recall = MemoryRecall(store, adapter, top_k=top_k)
        self._extractor = MemoryExtractor(store, adapter)
        self._consolidator = MemoryConsolidator(store, adapter)

    async def before_run(
        self, task: str, messages: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Inject relevant memories ahead of the first user message."""
        return await self._recall.inject(task, messages)

    async def after_run(
        self, task: str, messages: list[dict[str, Any]]
    ) -> list[Memory]:
        """Extract and persist new memories from a completed run."""
        return await self._extractor.extract(task, messages)

    async def consolidate(self) -> int:
        """Merge duplicates and prune stale memories.  Returns count removed."""
        return await self._consolidator.consolidate()
