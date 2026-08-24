"""Permission modes and tool permission categories.

Modes map to sets of allowed tool permissions:
    PLAN          → READ only        (explore, no changes)
    DEFAULT       → READ only        (same as plan for automated runs)
    ACCEPT_EDITS  → READ + EDIT      (file writes allowed)
    BYPASS        → READ + EDIT + EXECUTE (shell also allowed)
"""

from __future__ import annotations

from enum import Enum


class PermissionMode(str, Enum):
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    PLAN = "plan"
    BYPASS = "bypassPermissions"


class ToolPermission(str, Enum):
    READ = "read"        # list_directory, read_file
    EDIT = "edit"        # write_file
    EXECUTE = "execute"  # run_shell


_MODE_ALLOWS: dict[PermissionMode, frozenset[ToolPermission]] = {
    PermissionMode.PLAN:         frozenset({ToolPermission.READ}),
    PermissionMode.DEFAULT:      frozenset({ToolPermission.READ}),
    PermissionMode.ACCEPT_EDITS: frozenset({ToolPermission.READ, ToolPermission.EDIT}),
    PermissionMode.BYPASS:       frozenset({ToolPermission.READ, ToolPermission.EDIT, ToolPermission.EXECUTE}),
}


def is_allowed(mode: PermissionMode, permission: ToolPermission) -> bool:
    return permission in _MODE_ALLOWS[mode]
