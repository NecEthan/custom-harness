"""File system tools — read, write, list. Paths constrained to root dir."""

from __future__ import annotations

import os
from pathlib import Path

from harness.registry import ToolDefinition, ToolRegistry


def _safe_path(root: Path, relative: str) -> Path:
    """Resolve path and ensure it stays within root. Raises ValueError if not."""
    resolved = (root / relative).resolve()
    if not str(resolved).startswith(str(root.resolve())):
        raise ValueError(f"Path escapes root: {relative!r}")
    return resolved


def register_file_tools(registry: ToolRegistry, root: str | Path) -> None:
    root = Path(root).resolve()

    async def read_file(path: str) -> str:
        target = _safe_path(root, path)
        if not target.exists():
            raise FileNotFoundError(f"No such file: {path}")
        if not target.is_file():
            raise IsADirectoryError(f"Not a file: {path}")
        return target.read_text(encoding="utf-8")

    async def write_file(path: str, content: str) -> str:
        target = _safe_path(root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"

    async def list_directory(path: str = ".") -> str:
        target = _safe_path(root, path)
        if not target.exists():
            raise FileNotFoundError(f"No such directory: {path}")
        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")
        entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
        lines = []
        for entry in entries:
            kind = "file" if entry.is_file() else "dir "
            lines.append(f"{kind}  {entry.name}")
        return "\n".join(lines) if lines else "(empty)"

    registry.register(ToolDefinition(
        name="read_file",
        description="Read the contents of a file at the given path (relative to working root).",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"},
            },
            "required": ["path"],
        },
        fn=read_file,
    ))

    registry.register(ToolDefinition(
        name="write_file",
        description="Write content to a file at the given path (relative to working root). Creates parent directories.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"},
                "content": {"type": "string", "description": "Content to write"},
            },
            "required": ["path", "content"],
        },
        fn=write_file,
    ))

    registry.register(ToolDefinition(
        name="list_directory",
        description="List files and subdirectories at the given path (relative to working root).",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative directory path (default: '.')"},
            },
            "required": [],
        },
        fn=list_directory,
    ))
