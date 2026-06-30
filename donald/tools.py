"""Donald's tools — what lets him act, not just talk.

Custom (client-side) tools are executed here. `web_search` is a server-side
tool run by the API, so it has no executor — it just gets declared.

Safety model:
- read_file / web_search run automatically (read-only).
- write_file / run_shell can change your machine, so the CLI asks you to
  approve each call before it happens (see REQUIRES_APPROVAL).
- File access is confined to the current working directory; paths that try to
  escape it (via `..` or an absolute path) are rejected.
"""

from __future__ import annotations

import pathlib
import subprocess

from . import memory

MAX_OUTPUT_CHARS = 100_000
SHELL_TIMEOUT_S = 60

# Server-side tool: the API runs the search and returns results inline.
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}

# Client-side tools: Donald asks, we execute below.
CUSTOM_TOOLS = [
    {
        "name": "read_file",
        "description": (
            "Read a UTF-8 text file from the working directory and return its "
            "contents. Use this to inspect code, notes, or configs the operator "
            "asks about."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path, relative to the working directory.",
                }
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "write_file",
        "description": (
            "Create or overwrite a UTF-8 text file in the working directory. "
            "The operator approves before the write happens."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File path to write, relative to the working directory.",
                },
                "content": {
                    "type": "string",
                    "description": "Full contents to write.",
                },
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "remember",
        "description": (
            "Save a durable fact to long-term memory so you'll recall it in "
            "future sessions. Use for stable, useful things — the operator's "
            "name, preferences, ongoing projects, conventions. Not for "
            "ephemeral chatter. Phrase each note as a standalone fact."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "A single durable fact, phrased to stand on its own.",
                }
            },
            "required": ["note"],
            "additionalProperties": False,
        },
    },
    {
        "name": "update_memory",
        "description": (
            "Rewrite your entire long-term memory with a curated version. Use "
            "this to tidy up — merge duplicates, drop facts that are stale or no "
            "longer true, fix contradictions. You are given your current memory "
            "at the start of each session; pass the full revised set of facts, "
            "one per line, since this REPLACES everything. Passing empty clears "
            "it. The previous copy is backed up automatically."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The full revised memory, one durable fact per line.",
                }
            },
            "required": ["content"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_shell",
        "description": (
            "Run a shell command in the working directory and return its "
            "combined stdout/stderr and exit code. The operator approves before "
            "it runs. Use for builds, tests, git, listing files, and similar."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "The shell command to run.",
                }
            },
            "required": ["command"],
            "additionalProperties": False,
        },
    },
]

ALL_TOOLS = [*CUSTOM_TOOLS, WEB_SEARCH_TOOL]

# Tools that can change the machine — gated behind operator approval.
REQUIRES_APPROVAL = {"write_file", "run_shell"}


def describe(name: str, args: dict) -> str:
    """A short, human-readable summary of a tool call for display/approval."""
    if name == "read_file":
        return f"read {args.get('path')}"
    if name == "write_file":
        content = args.get("content", "")
        return f"write {args.get('path')} ({len(content)} chars)"
    if name == "run_shell":
        return f"run: {args.get('command')}"
    if name == "remember":
        return f"remember: {args.get('note')}"
    if name == "update_memory":
        return f"tidy memory ({len(args.get('content', ''))} chars)"
    return f"{name} {args}"


def _safe_path(path: str) -> pathlib.Path:
    """Resolve `path` and confirm it stays inside the working directory."""
    root = pathlib.Path.cwd().resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        raise ValueError(f"path escapes the working directory: {path}")
    return target


def _truncate(text: str) -> str:
    if len(text) > MAX_OUTPUT_CHARS:
        return text[:MAX_OUTPUT_CHARS] + "\n...[truncated]"
    return text


def _read_file(args: dict) -> tuple[str, bool]:
    target = _safe_path(args["path"])
    if not target.is_file():
        return f"No such file: {args['path']}", True
    return _truncate(target.read_text(encoding="utf-8", errors="replace")), False


def _write_file(args: dict) -> tuple[str, bool]:
    target = _safe_path(args["path"])
    target.parent.mkdir(parents=True, exist_ok=True)
    content = args["content"]
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} chars to {args['path']}", False


def _remember(args: dict) -> tuple[str, bool]:
    return memory.remember(args["note"]), False


def _update_memory(args: dict) -> tuple[str, bool]:
    return memory.replace(args["content"]), False


def _run_shell(args: dict) -> tuple[str, bool]:
    try:
        proc = subprocess.run(
            args["command"],
            shell=True,
            capture_output=True,
            text=True,
            timeout=SHELL_TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return f"Command timed out after {SHELL_TIMEOUT_S}s", True
    combined = (proc.stdout or "") + (proc.stderr or "")
    body = combined.strip() or "(no output)"
    # A non-zero exit is informative, not a tool failure — report it, don't flag it.
    return _truncate(f"exit code {proc.returncode}\n{body}"), False


_EXECUTORS = {
    "read_file": _read_file,
    "write_file": _write_file,
    "run_shell": _run_shell,
    "remember": _remember,
    "update_memory": _update_memory,
}


def execute(name: str, args: dict) -> tuple[str, bool]:
    """Run a client-side tool. Returns (result_text, is_error)."""
    executor = _EXECUTORS.get(name)
    if executor is None:
        return f"Unknown tool: {name}", True
    try:
        return executor(args)
    except Exception as exc:  # surface the failure to Donald, don't crash the REPL
        return f"{type(exc).__name__}: {exc}", True
