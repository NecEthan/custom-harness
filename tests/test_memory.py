"""Tests for the memory subsystem — store, recall, extraction, consolidation."""

from __future__ import annotations

import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from harness.adapter import ModelResponse, TextBlock
from harness.memory import MemoryManager, MemoryStore
from harness.memory.consolidation import MemoryConsolidator
from harness.memory.extraction import MemoryExtractor
from harness.memory.recall import MemoryRecall
from harness.memory.store import MemoryStore, _parse, _serialize
from harness.memory.types import Memory


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def text_response(text: str) -> ModelResponse:
    return ModelResponse(
        stop_reason="end_turn",
        content=[TextBlock(text=text)],
        input_tokens=10,
        output_tokens=5,
    )


def make_memory(**kwargs) -> Memory:
    defaults = dict(title="Test fact", body="Body text.", tags=["test"], importance=0.5)
    defaults.update(kwargs)
    return Memory(**defaults)


# ---------------------------------------------------------------------------
# MemoryStore — serialise / parse round-trip
# ---------------------------------------------------------------------------

def test_serialize_parse_roundtrip():
    m = make_memory(title="User prefers fixtures", tags=["testing", "preferences"])
    recovered = _parse(_serialize(m))
    assert recovered is not None
    assert recovered.id == m.id
    assert recovered.title == m.title
    assert recovered.body == m.body
    assert recovered.tags == m.tags
    assert abs(recovered.importance - m.importance) < 1e-6


def test_parse_returns_none_for_invalid_text():
    assert _parse("no frontmatter here") is None


def test_store_save_and_list(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = make_memory()
    store.save(m)
    memories = store.list()
    assert len(memories) == 1
    assert memories[0].id == m.id


def test_store_get(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = make_memory()
    store.save(m)
    retrieved = store.get(m.id)
    assert retrieved is not None
    assert retrieved.title == m.title


def test_store_get_missing_returns_none(tmp_path: Path):
    store = MemoryStore(tmp_path)
    assert store.get("nonexistent") is None


def test_store_delete(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = make_memory()
    store.save(m)
    store.delete(m.id)
    assert store.list() == []


def test_store_clear(tmp_path: Path):
    store = MemoryStore(tmp_path)
    for i in range(3):
        store.save(make_memory(title=f"Fact {i}"))
    store.clear()
    assert store.list() == []


def test_store_creates_directory(tmp_path: Path):
    nested = tmp_path / "a" / "b" / "memory"
    store = MemoryStore(nested)
    assert nested.exists()


# ---------------------------------------------------------------------------
# MemoryRecall
# ---------------------------------------------------------------------------

@pytest.fixture
def store_with_memories(tmp_path: Path) -> MemoryStore:
    store = MemoryStore(tmp_path)
    for i in range(3):
        store.save(make_memory(title=f"Fact {i}", id=f"id{i:06d}"))
    return store


async def test_recall_inject_no_memories(tmp_path: Path):
    store = MemoryStore(tmp_path)
    adapter = AsyncMock()
    recall = MemoryRecall(store, adapter, top_k=5)
    messages = [{"role": "user", "content": "hello"}]
    result = await recall.inject("hello", messages)
    assert result == messages  # unchanged


async def test_recall_inject_prepends_block(store_with_memories: MemoryStore):
    adapter = AsyncMock()
    recall = MemoryRecall(store_with_memories, adapter, top_k=10)
    messages = [{"role": "user", "content": "hello"}]
    result = await recall.inject("hello", messages)
    assert "<memory>" in result[0]["content"]
    assert "hello" in result[0]["content"]


async def test_recall_does_not_call_model_when_few_memories(store_with_memories: MemoryStore):
    """When len(memories) <= top_k, skip the ranking LLM call."""
    adapter = AsyncMock()
    recall = MemoryRecall(store_with_memories, adapter, top_k=10)
    await recall.inject("task", [{"role": "user", "content": "task"}])
    adapter.complete.assert_not_called()


async def test_recall_calls_model_to_rank_when_many_memories(tmp_path: Path):
    store = MemoryStore(tmp_path)
    for i in range(10):
        store.save(make_memory(id=f"id{i:06d}", title=f"Fact {i}"))

    adapter = AsyncMock()
    adapter.complete.return_value = text_response('["id000000", "id000001"]')
    recall = MemoryRecall(store, adapter, top_k=2)
    messages = [{"role": "user", "content": "task"}]
    result = await recall.inject("task", messages)
    adapter.complete.assert_called_once()
    # Only the 2 ranked memories appear in the block
    content: str = result[0]["content"]
    assert "id000000" in content
    assert "id000001" in content


async def test_recall_fallback_on_bad_json(tmp_path: Path):
    store = MemoryStore(tmp_path)
    for i in range(10):
        store.save(make_memory(id=f"id{i:06d}", title=f"Fact {i}"))

    adapter = AsyncMock()
    adapter.complete.return_value = text_response("not json")
    recall = MemoryRecall(store, adapter, top_k=3)
    # Should not raise — falls back to first N
    result = await recall.inject("task", [{"role": "user", "content": "task"}])
    assert "<memory>" in result[0]["content"]


# ---------------------------------------------------------------------------
# MemoryExtractor
# ---------------------------------------------------------------------------

async def test_extractor_saves_returned_memories(tmp_path: Path):
    store = MemoryStore(tmp_path)
    adapter = AsyncMock()
    adapter.complete.return_value = text_response(json.dumps([
        {"title": "Prefer fixtures", "body": "Use pytest fixtures.", "tags": ["testing"], "importance": 0.8},
    ]))
    extractor = MemoryExtractor(store, adapter)
    saved = await extractor.extract("task", [{"role": "user", "content": "task"}])
    assert len(saved) == 1
    assert saved[0].title == "Prefer fixtures"
    assert store.get(saved[0].id) is not None


async def test_extractor_handles_empty_array(tmp_path: Path):
    store = MemoryStore(tmp_path)
    adapter = AsyncMock()
    adapter.complete.return_value = text_response("[]")
    extractor = MemoryExtractor(store, adapter)
    saved = await extractor.extract("task", [{"role": "user", "content": "task"}])
    assert saved == []
    assert store.list() == []


async def test_extractor_handles_bad_json(tmp_path: Path):
    store = MemoryStore(tmp_path)
    adapter = AsyncMock()
    adapter.complete.return_value = text_response("not json at all")
    extractor = MemoryExtractor(store, adapter)
    saved = await extractor.extract("task", [{"role": "user", "content": "task"}])
    assert saved == []


async def test_extractor_skips_items_missing_title_or_body(tmp_path: Path):
    store = MemoryStore(tmp_path)
    adapter = AsyncMock()
    adapter.complete.return_value = text_response(json.dumps([
        {"title": "", "body": "some body", "tags": [], "importance": 0.5},
        {"title": "Good one", "body": "Good body.", "tags": [], "importance": 0.5},
    ]))
    extractor = MemoryExtractor(store, adapter)
    saved = await extractor.extract("task", [{"role": "user", "content": "task"}])
    assert len(saved) == 1
    assert saved[0].title == "Good one"


# ---------------------------------------------------------------------------
# MemoryConsolidator
# ---------------------------------------------------------------------------

async def test_consolidator_rewrites_store(tmp_path: Path):
    store = MemoryStore(tmp_path)
    store.save(make_memory(id="aaa00001", title="Dup A", body="Body A."))
    store.save(make_memory(id="aaa00002", title="Dup B", body="Body B."))

    adapter = AsyncMock()
    adapter.complete.return_value = text_response(json.dumps([
        {"title": "Merged A+B", "body": "Combined body.", "tags": [], "importance": 0.6},
    ]))
    consolidator = MemoryConsolidator(store, adapter)
    removed = await consolidator.consolidate()

    assert removed == 1          # 2 in, 1 out
    memories = store.list()
    assert len(memories) == 1
    assert memories[0].title == "Merged A+B"


async def test_consolidator_preserves_id_when_unchanged(tmp_path: Path):
    store = MemoryStore(tmp_path)
    m = make_memory(id="keepme01", title="Keep me", body="Still valid.")
    store.save(m)
    store.save(make_memory(id="dropme01", title="Stale", body="Old info."))

    adapter = AsyncMock()
    adapter.complete.return_value = text_response(json.dumps([
        {"id": "keepme01", "title": "Keep me", "body": "Still valid.", "tags": [], "importance": 0.7},
    ]))
    consolidator = MemoryConsolidator(store, adapter)
    await consolidator.consolidate()

    kept = store.get("keepme01")
    assert kept is not None
    assert kept.created == m.created  # timestamps preserved


async def test_consolidator_skips_when_less_than_two(tmp_path: Path):
    store = MemoryStore(tmp_path)
    store.save(make_memory())
    adapter = AsyncMock()
    consolidator = MemoryConsolidator(store, adapter)
    removed = await consolidator.consolidate()
    assert removed == 0
    adapter.complete.assert_not_called()


# ---------------------------------------------------------------------------
# MemoryManager integration with AgentLoop
# ---------------------------------------------------------------------------

async def test_loop_calls_before_and_after_run(tmp_path: Path):
    from unittest.mock import patch
    from harness.loop import AgentLoop, LoopConfig
    from harness.registry import ToolRegistry

    store = MemoryStore(tmp_path)
    manager = MemoryManager.__new__(MemoryManager)
    manager.before_run = AsyncMock(side_effect=lambda task, msgs: msgs)
    manager.after_run = AsyncMock(return_value=[])

    registry = ToolRegistry()
    config = LoopConfig(max_turns=1)
    loop = AgentLoop(registry, config=config, memory=manager)

    with patch.object(
        loop._adapter, "complete",
        new=AsyncMock(return_value=ModelResponse(
            stop_reason="end_turn",
            content=[TextBlock(text="done")],
            input_tokens=10,
            output_tokens=5,
        )),
    ):
        await loop.run("task")

    manager.before_run.assert_called_once()
    manager.after_run.assert_called_once()


async def test_loop_after_run_failure_does_not_propagate(tmp_path: Path):
    from harness.loop import AgentLoop, LoopConfig
    from harness.registry import ToolRegistry

    store = MemoryStore(tmp_path)
    manager = MemoryManager.__new__(MemoryManager)
    manager.before_run = AsyncMock(side_effect=lambda task, msgs: msgs)
    manager.after_run = AsyncMock(side_effect=RuntimeError("extraction failed"))

    registry = ToolRegistry()
    loop = AgentLoop(registry, LoopConfig(max_turns=1), memory=manager)

    with patch.object(
        loop._adapter, "complete",
        new=AsyncMock(return_value=ModelResponse(
            stop_reason="end_turn",
            content=[TextBlock(text="done")],
            input_tokens=10,
            output_tokens=5,
        )),
    ):
        result = await loop.run("task")  # must not raise

    assert result.final_text == "done"
