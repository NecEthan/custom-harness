"""Convert harness events to JSON-serializable dicts for SSE transport.

Single source of truth — no separate event model that can drift from events.py.
"""

from __future__ import annotations

import dataclasses
import json
from typing import Any

from harness.events import Event


def event_to_dict(event: Event) -> dict[str, Any]:
    """Flatten event dataclass to dict and inject a 'type' discriminator field."""
    d = dataclasses.asdict(event)
    d["type"] = type(event).__name__
    return d


def event_to_json(event: Event) -> str:
    return json.dumps(event_to_dict(event))


def sse_message(event: Event) -> str:
    """Format as an SSE data frame (ends with double newline)."""
    return f"data: {event_to_json(event)}\n\n"
