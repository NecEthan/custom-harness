"""Minimal CLI entrypoint for manual testing."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from harness.events import (
    AgentFinished, Event, ToolCalled, ToolResulted, TurnEnded, TurnStarted,
)
from harness.loop import AgentLoop, LoopConfig
from harness.registry import ToolRegistry
from harness.tools.file import register_file_tools
from harness.tools.shell import register_shell_tools

load_dotenv()


async def log_event(event: Event) -> None:
    match event:
        case TurnStarted(turn=t):
            print(f"\n--- turn {t} ---")
        case ToolCalled(name=n, input=inp):
            print(f"  tool call: {n}({inp})")
        case ToolResulted(name=n, output=out, is_error=err):
            status = "ERROR" if err else "ok"
            preview = out[:120].replace("\n", "\\n")
            print(f"  tool result [{status}]: {preview}")
        case TurnEnded(stop_reason=r, text=t) if t:
            print(f"  [{r}] {t[:200]}")
        case AgentFinished(total_turns=t):
            print(f"\nfinished in {t} turn(s)")


async def main() -> None:
    task = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "List the files in the current directory."
    work_dir = Path.cwd()

    registry = ToolRegistry() 
    register_file_tools(registry, root=work_dir)
    register_shell_tools(registry, timeout=30)

    from harness.events import EventBus
    bus = EventBus()
    bus.subscribe(log_event)

    loop = AgentLoop(
        registry=registry,
        config=LoopConfig(max_turns=10),
        bus=bus,
    )

    print(f"task: {task}")
    result = await loop.run(task)

    print(f"\ntokens: {result.total_input_tokens} in / {result.total_output_tokens} out")


if __name__ == "__main__":
    asyncio.run(main())
