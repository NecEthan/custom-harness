"""Error classification for the agent loop.

Classify an exception into a failure layer first, then decide whether to
retry, adjust, or stop — never count retries before knowing the layer.

Layers
------
API      Transient: rate limits, timeouts, overload. Retry with backoff.
CONTEXT  Prompt too long or message history rejected. Condense, then retry.
FATAL    Not recoverable: auth errors, bad schemas, unknown errors. Stop.
"""

from __future__ import annotations

from enum import Enum

import anthropic


class FailureLayer(str, Enum):
    API = "api"
    CONTEXT = "context"
    FATAL = "fatal"


def classify(exc: Exception) -> FailureLayer:
    """Return the failure layer for an exception raised by the Anthropic adapter."""
    if isinstance(exc, (
        anthropic.RateLimitError,
        anthropic.APITimeoutError,
        anthropic.APIConnectionError,
        anthropic.InternalServerError,  # includes 529 overloaded
    )):
        return FailureLayer.API

    if isinstance(exc, anthropic.BadRequestError):
        msg = str(exc).lower()
        if "prompt is too long" in msg or "too many tokens" in msg:
            return FailureLayer.CONTEXT
        return FailureLayer.FATAL

    return FailureLayer.FATAL
