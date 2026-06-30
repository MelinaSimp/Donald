"""Tier 3 — spawn Claude Code as a subprocess (the composition step).

The planning agent stays cheap (Sonnet, the Anthropic SDK). The *composition*
shells out to the ``claude`` CLI, which runs in the project root with narrow Bash
permissions and reads the on-disk component catalog. This module is the single
driver for that subprocess.

Design points:
  * stdlib only — no SDK. The CLI is invoked with ``--output-format stream-json``
    and the NDJSON event stream is drained line by line, each forwarded through
    ``on_event`` so a UI can show "[CC] Read design.md", "[CC] npm run build", …
  * env is sanitized to an allowlist (``config.CHILD_ENV_ALLOWLIST``) so no other
    secret leaks into the child.
  * a clean ``ClaudeCodeResult`` dataclass is returned regardless of outcome.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from . import config

OnEvent = Callable[[dict], None]


@dataclass
class ClaudeCodeResult:
    ok: bool
    returncode: int
    events: list[dict] = field(default_factory=list)
    # The assistant's final text (CLI "result" event), if any.
    result_text: str = ""
    # Tool calls observed in the stream, e.g. ("Read", "Write", "Bash"), useful
    # for asserting "did CC actually read the references / write the page".
    tool_uses: list[dict] = field(default_factory=list)
    error: str = ""
    command: list[str] = field(default_factory=list)


class ClaudeCodeNotFound(RuntimeError):
    """The ``claude`` binary is not on PATH."""


# ---------------------------------------------------------------------------
# Env sanitation
# ---------------------------------------------------------------------------


def sanitize_env(
    base: dict | None = None,
    allowlist: Sequence[str] = config.CHILD_ENV_ALLOWLIST,
) -> dict[str, str]:
    """Return a minimal env carrying only the allowlisted vars that are set."""
    src = os.environ if base is None else base
    return {k: src[k] for k in allowlist if k in src and src[k] is not None}


# ---------------------------------------------------------------------------
# Command construction
# ---------------------------------------------------------------------------


def build_command(
    prompt: str,
    model: str,
    max_turns: int,
    allowed_tools: Sequence[str],
    binary: str = "claude",
) -> list[str]:
    return [
        binary,
        "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--model", model,
        "--max-turns", str(max_turns),
        "--allowedTools", ",".join(allowed_tools),
    ]


# ---------------------------------------------------------------------------
# Stream parsing
# ---------------------------------------------------------------------------


def _extract_tool_uses(event: dict) -> list[dict]:
    """Pull tool_use blocks out of an assistant message event."""
    uses: list[dict] = []
    msg = event.get("message") if isinstance(event.get("message"), dict) else None
    content = (msg or {}).get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                uses.append({"name": block.get("name", ""), "input": block.get("input", {})})
    return uses


def _consume_stream(
    stream, on_event: OnEvent | None, result: ClaudeCodeResult
) -> None:
    for raw in stream:
        line = raw.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # Non-JSON line (e.g. a stray log); forward as a synthetic event.
            event = {"type": "raw", "text": line}
        result.events.append(event)
        if event.get("type") == "assistant":
            result.tool_uses.extend(_extract_tool_uses(event))
        if event.get("type") == "result":
            # CLI final event; may carry the result text under "result".
            txt = event.get("result")
            if isinstance(txt, str):
                result.result_text = txt
        if on_event is not None:
            on_event(event)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def spawn_claude_code(
    prompt: str,
    cwd: str | Path,
    model: str | None = None,
    max_turns: int = 40,
    allowed_tools: Sequence[str] | None = None,
    on_event: OnEvent | None = None,
    *,
    binary: str = "claude",
    timeout: float | None = None,
    _popen=subprocess.Popen,  # injectable for tests
) -> ClaudeCodeResult:
    """Run Claude Code headlessly in ``cwd``; drain its NDJSON stream.

    ``_popen`` is injectable so unit tests can drive the parser without a real
    ``claude`` binary. In production it is ``subprocess.Popen``.
    """
    model = model or config.DEFAULT_COMPOSER_MODEL
    allowed_tools = list(allowed_tools or DEFAULT_ALLOWED_TOOLS)
    cmd = build_command(prompt, model, max_turns, allowed_tools, binary=binary)

    if _popen is subprocess.Popen and shutil.which(binary) is None:
        raise ClaudeCodeNotFound(
            f"'{binary}' not found on PATH. Install the Claude Code CLI to compose mockups."
        )

    env = sanitize_env()
    result = ClaudeCodeResult(ok=False, returncode=-1, command=cmd)

    try:
        proc = _popen(
            cmd,
            cwd=str(cwd),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:  # pragma: no cover - guarded above
        raise ClaudeCodeNotFound(str(exc)) from exc

    try:
        if proc.stdout is not None:
            _consume_stream(proc.stdout, on_event, result)
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        result.error = f"claude code timed out after {timeout}s"
    finally:
        if proc.stderr is not None:
            try:
                err = proc.stderr.read()
                if err and not result.error:
                    result.error = err.strip()
            except Exception:  # pragma: no cover - defensive
                pass

    result.returncode = proc.returncode if proc.returncode is not None else -1
    result.ok = result.returncode == 0 and not result.error
    return result


# The narrow-but-functional tool list CC is allowed to use. Scoped to the Bash
# prefixes the build actually needs — never Bash(*), never no-Bash.
DEFAULT_ALLOWED_TOOLS: list[str] = [
    "Read", "Write", "Edit", "Glob", "Grep",
    "Bash(npm install:*)",
    "Bash(npm run:*)",
    "Bash(npx shadcn:*)",
    "Bash(npx shadcn@latest:*)",
    "Bash(npx magicui-cli:*)",
    "Bash(next build:*)",
    "Bash(next export:*)",
    "Bash(ls:*)",
    "Bash(mkdir:*)",
    "Bash(cat:*)",
]
