"""File system tools — read, write, list. Paths constrained to root dir."""

from __future__ import annotations

import json
from pathlib import Path

from harness.permissions import ToolPermission
from harness.registry import ToolDefinition, ToolRegistry

MAX_LINES = 200
MAX_DIR_ENTRIES = 200
MAX_FIND_RESULTS = 500


def _safe_path(root: Path, relative: str) -> Path:
    """Resolve path and ensure it stays within root. Raises ValueError if not."""
    resolved = (root / relative).resolve()
    if not str(resolved).startswith(str(root.resolve())):
        raise ValueError(f"Path escapes root: {relative!r}")
    return resolved


def register_file_tools(registry: ToolRegistry, root: str | Path) -> None:
    root = Path(root).resolve()

    async def read_file(path: str, start_line: int = 1) -> str:
        target = _safe_path(root, path)
        if not target.exists():
            raise FileNotFoundError(f"No such file: {path}")
        if not target.is_file():
            raise IsADirectoryError(f"Not a file: {path}")

        all_lines = target.read_text(encoding="utf-8").splitlines(keepends=True)
        total_lines = len(all_lines)

        # Clamp start_line to valid range (1-indexed)
        start_idx = max(0, start_line - 1)
        chunk = all_lines[start_idx : start_idx + MAX_LINES]
        end_line = start_idx + len(chunk)
        truncated = end_line < total_lines

        result: dict = {
            "path": path,
            "total_lines": total_lines,
            "start_line": start_idx + 1,
            "end_line": end_line,
            "content": "".join(chunk),
        }
        if truncated:
            result["truncated"] = True
            result["message"] = (
                f"Reached max lines per read ({MAX_LINES}). "
                f"File has {total_lines} lines total. "
                f"Call read_file again with start_line={end_line + 1} to read the next chunk."
            )
        return json.dumps(result)

    async def write_file(path: str, content: str) -> str:
        target = _safe_path(root, path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} bytes to {path}"

    async def list_directory(path: str = ".", offset: int = 0) -> str:
        target = _safe_path(root, path)
        if not target.exists():
            raise FileNotFoundError(f"No such directory: {path}")
        if not target.is_dir():
            raise NotADirectoryError(f"Not a directory: {path}")

        all_entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
        total = len(all_entries)
        chunk = all_entries[offset : offset + MAX_DIR_ENTRIES]
        shown = len(chunk)
        truncated = (offset + shown) < total

        lines = []
        for entry in chunk:
            kind = "file" if entry.is_file() else "dir "
            lines.append(f"{kind}  {entry.name}")

        result: dict = {
            "path": path,
            "total_entries": total,
            "offset": offset,
            "shown": shown,
            "entries": "\n".join(lines) if lines else "(empty)",
        }
        if truncated:
            result["truncated"] = True
            result["message"] = (
                f"Directory has {total} entries. Showing {offset + 1}-{offset + shown}. "
                f"Call list_directory again with offset={offset + shown} to see more."
            )
        return json.dumps(result)

    registry.register(ToolDefinition(
        name="read_file",
        description=(
            f"Read up to {MAX_LINES} lines of a file at the given path (relative to working root). "
            "Returns JSON with total_lines, start_line, end_line, content, and a message if the file "
            "was truncated. If truncated, call again with start_line set to the next unread line."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"},
                "start_line": {
                    "type": "integer",
                    "description": f"1-indexed line to start reading from (default: 1). Use to paginate large files.",
                },
            },
            "required": ["path"],
        },
        fn=read_file,
        permission=ToolPermission.READ,
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
        permission=ToolPermission.EDIT,
    ))

    async def find_files(pattern: str = "**/*", path: str = ".") -> str:
        base = _safe_path(root, path)
        if not base.exists():
            raise FileNotFoundError(f"No such directory: {path}")

        matches = sorted(base.glob(pattern))
        # Strip root prefix for readability
        entries = []
        for m in matches[:MAX_FIND_RESULTS]:
            rel = m.relative_to(root)
            kind = "file" if m.is_file() else "dir "
            entries.append(f"{kind}  {rel}")

        result: dict = {
            "pattern": pattern,
            "base": path,
            "count": len(entries),
            "paths": "\n".join(entries) if entries else "(no matches)",
        }
        if len(matches) > MAX_FIND_RESULTS:
            result["truncated"] = True
            result["message"] = f"Returned first {MAX_FIND_RESULTS} of {len(matches)} matches. Narrow the pattern."
        return json.dumps(result)

    registry.register(ToolDefinition(
        name="find_files",
        description=(
            "Recursively search for files/directories matching a glob pattern under a base path. "
            "Returns all matches in one call — use this instead of repeated list_directory calls. "
            "Examples: pattern='**/*.py' finds all Python files, pattern='**/api*' finds API-related paths. "
            f"Returns up to {MAX_FIND_RESULTS} results."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Glob pattern (default: '**/*' for all files). E.g. '**/*.py', 'src/**/*.ts'",
                },
                "path": {
                    "type": "string",
                    "description": "Base directory to search from (default: '.')",
                },
            },
            "required": [],
        },
        fn=find_files,
        permission=ToolPermission.READ,
    ))

    registry.register(ToolDefinition(
        name="list_directory",
        description=(
            f"List entries in a single directory (non-recursive). "
            "For exploring a tree or finding files across subdirectories, prefer find_files instead. "
            "Returns JSON with total_entries, offset, shown, entries. If truncated, call again with next offset."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative directory path (default: '.')"},
                "offset": {
                    "type": "integer",
                    "description": f"0-indexed entry to start from (default: 0). Use to paginate large directories.",
                },
            },
            "required": [],
        },
        fn=list_directory,
        permission=ToolPermission.READ,
    ))
