"""Tests for file system tools."""

import json

import pytest
from harness.registry import ToolRegistry
from harness.tools.file import MAX_LINES, register_file_tools


@pytest.fixture
def registry(tmp_path):
    r = ToolRegistry()
    register_file_tools(r, root=tmp_path)
    return r, tmp_path


async def test_write_and_read(registry):
    r, root = registry
    result = await r.call("write_file", "w1", {"path": "hello.txt", "content": "world"})
    assert not result.is_error
    assert "5 bytes" in result.output

    result = await r.call("read_file", "r1", {"path": "hello.txt"})
    assert not result.is_error
    data = json.loads(result.output)
    assert data["content"] == "world"
    assert data["total_lines"] == 1
    assert data["start_line"] == 1
    assert data["end_line"] == 1
    assert "truncated" not in data


async def test_read_missing_file(registry):
    r, _ = registry
    result = await r.call("read_file", "r2", {"path": "missing.txt"})
    assert result.is_error
    assert "FileNotFoundError" in result.output


async def test_list_directory(registry):
    r, root = registry
    (root / "a.txt").write_text("a")
    (root / "b.txt").write_text("b")
    result = await r.call("list_directory", "l1", {"path": "."})
    assert not result.is_error
    data = json.loads(result.output)
    assert "a.txt" in data["entries"]
    assert "b.txt" in data["entries"]
    assert data["total_entries"] == 2
    assert "truncated" not in data


async def test_list_directory_truncated(registry):
    r, root = registry
    for i in range(MAX_LINES + 5):  # reuse MAX_LINES as a large number
        (root / f"file_{i:04d}.txt").write_text("")

    from harness.tools.file import MAX_DIR_ENTRIES
    result = await r.call("list_directory", "l2", {"path": "."})
    assert not result.is_error
    data = json.loads(result.output)
    assert data["truncated"] is True
    assert data["total_entries"] == MAX_LINES + 5
    assert data["shown"] == MAX_DIR_ENTRIES
    assert f"offset={MAX_DIR_ENTRIES}" in data["message"]


async def test_list_directory_pagination(registry):
    r, root = registry
    from harness.tools.file import MAX_DIR_ENTRIES
    for i in range(MAX_DIR_ENTRIES + 3):
        (root / f"file_{i:04d}.txt").write_text("")

    result = await r.call("list_directory", "l3", {"path": ".", "offset": MAX_DIR_ENTRIES})
    assert not result.is_error
    data = json.loads(result.output)
    assert data["offset"] == MAX_DIR_ENTRIES
    assert data["shown"] == 3
    assert "truncated" not in data


async def test_path_escape_blocked(registry):
    r, _ = registry
    result = await r.call("read_file", "r3", {"path": "../../etc/passwd"})
    assert result.is_error
    assert "ValueError" in result.output


async def test_write_creates_parent_dirs(registry):
    r, root = registry
    result = await r.call("write_file", "w2", {
        "path": "subdir/nested/file.txt",
        "content": "deep",
    })
    assert not result.is_error
    assert (root / "subdir" / "nested" / "file.txt").read_text() == "deep"


async def test_read_file_truncated_when_over_max_lines(registry):
    r, root = registry
    lines = [f"line {i}\n" for i in range(1, MAX_LINES + 10)]
    (root / "big.txt").write_text("".join(lines))

    result = await r.call("read_file", "r4", {"path": "big.txt"})
    assert not result.is_error
    data = json.loads(result.output)
    assert data["truncated"] is True
    assert data["total_lines"] == MAX_LINES + 9
    assert data["end_line"] == MAX_LINES
    assert f"start_line={MAX_LINES + 1}" in data["message"]


async def test_read_file_pagination(registry):
    r, root = registry
    lines = [f"line {i}\n" for i in range(1, MAX_LINES + 10)]
    (root / "big.txt").write_text("".join(lines))

    # Read second chunk
    result = await r.call("read_file", "r5", {"path": "big.txt", "start_line": MAX_LINES + 1})
    assert not result.is_error
    data = json.loads(result.output)
    assert data["start_line"] == MAX_LINES + 1
    assert data["end_line"] == MAX_LINES + 9
    assert "truncated" not in data
    assert f"line {MAX_LINES + 1}" in data["content"]


async def test_read_file_reports_total_lines(registry):
    r, root = registry
    (root / "counted.txt").write_text("a\nb\nc\n")

    result = await r.call("read_file", "r6", {"path": "counted.txt"})
    data = json.loads(result.output)
    assert data["total_lines"] == 3
