"""Memory entry dataclass."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _new_id() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class Memory:
    title: str
    body: str
    id: str = field(default_factory=_new_id)
    tags: list[str] = field(default_factory=list)
    created: str = field(default_factory=_now)
    last_used: str = field(default_factory=_now)
    importance: float = 0.5   # 0.0 (trivial) – 1.0 (critical)
