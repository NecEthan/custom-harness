"""Immutable event dataclasses and a simple async event bus."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable


# ---------------------------------------------------------------------------
# Event types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TurnStarted:
    turn: int
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ToolCalled:
    turn: int
    tool_use_id: str
    name: str
    input: dict[str, Any]
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class ToolResulted:
    turn: int
    tool_use_id: str
    name: str
    output: str
    is_error: bool
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class TurnEnded:
    turn: int
    stop_reason: str
    text: str
    timestamp: float = field(default_factory=time.time)


@dataclass(frozen=True)
class AgentFinished:
    total_turns: int
    final_text: str
    timestamp: float = field(default_factory=time.time)


Event = TurnStarted | ToolCalled | ToolResulted | TurnEnded | AgentFinished

# ---------------------------------------------------------------------------
# Event bus
# ---------------------------------------------------------------------------

Subscriber = Callable[[Event], Awaitable[None]]


class EventBus:
    def __init__(self) -> None:
        self._subscribers: list[Subscriber] = []

    def subscribe(self, fn: Subscriber) -> None:
        self._subscribers.append(fn)

    async def emit(self, event: Event) -> None:
        for fn in self._subscribers:
            await fn(event)
