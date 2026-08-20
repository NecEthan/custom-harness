"""Tests for file system tools."""

import pytest
from harness.registry import ToolRegistry
from harness.tools.file import register_file_tools


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
    assert result.output == "world"
    assert not result.is_error


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
    assert "a.txt" in result.output
    assert "b.txt" in result.output


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
