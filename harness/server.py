"""Lightweight FastAPI server — SSE endpoint that streams EventBus events to the React UI.

Architecture:
    AgentLoop → EventBus → SSE subscriber → React frontend

The AgentLoop does not know this server exists. The EventBus is independent.
This module is simply another EventBus subscriber that forwards events over HTTP.
"""

from __future__ import annotations

import asyncio

from dotenv import load_dotenv
load_dotenv()  # pick up ANTHROPIC_API_KEY from .env if present
import json
from dataclasses import dataclass, field
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from harness.events import Event, EventBus
from harness.loop import AgentLoop, LoopConfig
from harness.permissions import PermissionMode
from harness.registry import ToolRegistry
from harness.serialization import event_to_dict
from harness.tools.file import register_file_tools
from harness.tools.shell import register_shell_tools


# ---------------------------------------------------------------------------
# In-memory run state
# ---------------------------------------------------------------------------

@dataclass
class RunState:
    task: str
    events: list[dict] = field(default_factory=list)   # replay buffer for late joiners
    queues: list[asyncio.Queue] = field(default_factory=list)  # one per live SSE client
    done: bool = False


_current_run: RunState | None = None
_run_lock: asyncio.Lock = asyncio.Lock()


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="custom-harness observability", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    task: str
    max_turns: int = 20
    work_dir: str = "."
    permission_mode: PermissionMode = PermissionMode.DEFAULT


# ---------------------------------------------------------------------------
# Background run executor
# ---------------------------------------------------------------------------

async def _execute_run(state: RunState, task: str, max_turns: int, work_dir: str, permission_mode: PermissionMode = PermissionMode.DEFAULT) -> None:
    """Run the agent and push every EventBus event to all connected SSE clients."""

    async def push(event: Event) -> None:
        d = event_to_dict(event)
        state.events.append(d)
        for q in list(state.queues):  # copy — queues may be removed mid-iteration
            await q.put(d)

    bus = EventBus()
    bus.subscribe(push)

    root = Path(work_dir).resolve()
    registry = ToolRegistry(mode=permission_mode)
    register_file_tools(registry, root=root)
    register_shell_tools(registry, timeout=30)

    loop = AgentLoop(
        registry=registry,
        config=LoopConfig(max_turns=max_turns),
        bus=bus,
    )

    try:
        await loop.run(task)
    finally:
        state.done = True
        for q in list(state.queues):
            await q.put(None)  # sentinel — signals SSE generator to close


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.post("/run", status_code=202)
async def start_run(body: RunRequest, background_tasks: BackgroundTasks):
    """Start an agent run. Returns immediately; run executes in the background."""
    global _current_run
    async with _run_lock:
        _current_run = RunState(task=body.task)
        background_tasks.add_task(
            _execute_run,
            _current_run,
            body.task,
            body.max_turns,
            body.work_dir,
            body.permission_mode,
        )
    return {"status": "started", "task": body.task}


@app.get("/run/events")
async def stream_events():
    """SSE endpoint — streams events as they are emitted by the EventBus.

    Late-joining clients receive all accumulated events first (catch-up replay),
    then live events as they arrive.
    """
    global _current_run
    if _current_run is None:
        raise HTTPException(status_code=404, detail="No active run. POST /run first.")

    run = _current_run
    queue: asyncio.Queue = asyncio.Queue()

    # Snapshot catch-up events and done flag atomically before registering queue,
    # so we don't miss events emitted between snapshot and registration.
    catch_up = list(run.events)
    already_done = run.done

    if not already_done:
        run.queues.append(queue)

    async def generate():
        try:
            for evt in catch_up:
                yield f"data: {json.dumps(evt)}\n\n"

            if already_done:
                return

            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=60.0)
                except asyncio.TimeoutError:
                    # Keep-alive ping
                    yield ": ping\n\n"
                    continue

                if item is None:  # sentinel
                    break
                yield f"data: {json.dumps(item)}\n\n"
        finally:
            if queue in run.queues:
                run.queues.remove(queue)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@app.get("/run/state")
async def get_run_state():
    """Return all accumulated events for the current run (polling fallback / testing)."""
    if _current_run is None:
        raise HTTPException(status_code=404, detail="No active run.")
    return {
        "task": _current_run.task,
        "done": _current_run.done,
        "event_count": len(_current_run.events),
        "events": _current_run.events,
    }


@app.get("/health")
async def health():
    return {"status": "ok"}
