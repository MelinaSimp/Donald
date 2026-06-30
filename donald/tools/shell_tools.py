"""Tier 1 tools — file access and shell, confined to Donald's workspace.

These are the powerful, world-changing tools, so they are deliberately narrow:
all paths are resolved *inside* the configured workspace and anything escaping
it is refused here (and again by the Tier 5 safety gate). Writes and shell runs
are marked ``mutating`` so safety scrutinises them.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .base import Registry, Tool, ToolError


def register(reg: Registry) -> None:
    reg.register(
        Tool(
            name="read_file",
            description="Read a UTF-8 text file from Donald's workspace.",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            func=read_file,
        )
    )
    reg.register(
        Tool(
            name="list_dir",
            description="List files and folders in a workspace directory ('.' for root).",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
            func=list_dir,
        )
    )
    reg.register(
        Tool(
            name="write_file",
            description="Create or overwrite a text file in Donald's workspace.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
            func=write_file,
            mutating=True,
        )
    )
    reg.register(
        Tool(
            name="run_shell",
            description=(
                "Run a shell command inside Donald's workspace and return its "
                "output. Use sparingly; destructive commands are blocked."
            ),
            input_schema={
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
            func=run_shell,
            mutating=True,
        )
    )


def _resolve(ctx, path: str) -> Path:
    root = Path(ctx.config.workspace).resolve()
    target = (root / path).resolve()
    if root != target and root not in target.parents:
        raise ToolError(f"Path '{path}' is outside the workspace; refused.")
    return target


def read_file(path: str, ctx) -> str:
    target = _resolve(ctx, path)
    if not target.is_file():
        raise ToolError(f"No such file: {path}")
    text = target.read_text(encoding="utf-8", errors="replace")
    if len(text) > 20000:
        text = text[:20000] + "\n…(truncated)"
    return text


def list_dir(ctx, path: str = ".") -> str:
    target = _resolve(ctx, path)
    if not target.is_dir():
        raise ToolError(f"Not a directory: {path}")
    entries = sorted(target.iterdir(), key=lambda p: (p.is_file(), p.name))
    if not entries:
        return "(empty)"
    return "\n".join(
        f"{'d' if p.is_dir() else 'f'}  {p.name}" for p in entries
    )


def write_file(path: str, content: str, ctx) -> str:
    target = _resolve(ctx, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return f"Wrote {len(content)} bytes to {path}."


def run_shell(command: str, ctx) -> str:
    root = Path(ctx.config.workspace).resolve()
    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired:
        raise ToolError("Command timed out after 30s.")
    out = (proc.stdout or "") + (proc.stderr or "")
    out = out.strip() or "(no output)"
    if len(out) > 10000:
        out = out[:10000] + "\n…(truncated)"
    return f"(exit {proc.returncode})\n{out}"
