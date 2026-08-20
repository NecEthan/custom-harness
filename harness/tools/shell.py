"""Shell tool — run subprocess commands with timeout. No shell=True."""

from __future__ import annotations

import asyncio
import shlex

from harness.registry import ToolDefinition, ToolRegistry

DEFAULT_TIMEOUT = 30  # seconds
MAX_OUTPUT_BYTES = 32_768


def register_shell_tools(
    registry: ToolRegistry,
    timeout: int = DEFAULT_TIMEOUT,
    allowed_commands: list[str] | None = None,
) -> None:
    """Register run_shell tool.

    Args:
        registry: Target registry.
        timeout: Per-command timeout in seconds.
        allowed_commands: Whitelist of allowed executable names.
                          None means no restriction (use with caution).
    """

    async def run_shell(command: str) -> str:
        args = shlex.split(command)
        if not args:
            return "(empty command)"

        executable = args[0]
        if allowed_commands is not None and executable not in allowed_commands:
            raise PermissionError(
                f"Command not allowed: {executable!r}. "
                f"Allowed: {sorted(allowed_commands)}"
            )

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            proc.kill()
            return f"(timeout after {timeout}s)"

        out = stdout.decode("utf-8", errors="replace")[:MAX_OUTPUT_BYTES]
        err = stderr.decode("utf-8", errors="replace")[:MAX_OUTPUT_BYTES]

        parts = []
        if out:
            parts.append(out)
        if err:
            parts.append(f"[stderr]\n{err}")
        parts.append(f"[exit {proc.returncode}]")
        return "\n".join(parts)

    registry.register(ToolDefinition(
        name="run_shell",
        description=(
            "Run a shell command and return stdout, stderr, and exit code. "
            "Use for running tests, listing files, compiling, etc."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute (parsed safely, no shell expansion)",
                },
            },
            "required": ["command"],
        },
        fn=run_shell,
    ))
