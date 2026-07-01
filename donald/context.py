"""Ambient context — what Donald knows without being told.

The difference between a voice command line and something Jarvis-like is that
Jarvis knows what you're *doing*, not just what you *say*. This module snapshots
your situation — time, machine, the app you're actually looking at — and the
brain injects it every turn, so Donald can say "you left the deploy half-
finished" instead of waiting to be spelled everything out.

Collection is best-effort and OS-aware: if a probe fails (no window server, a
tool missing), that field is simply absent — never an error. The formatter is
pure, so the wiring is testable without a desktop.
"""

from __future__ import annotations

import subprocess
from datetime import datetime
from typing import Optional

from .hermes.engine import detect_platform


def _run(cmd: list, timeout: float = 2.0) -> Optional[str]:
    """Best-effort shell probe: return stripped stdout, or None on any failure."""
    try:
        out = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        ).stdout.strip()
        return out or None
    except Exception:
        return None


def active_window(platform: Optional[str] = None) -> Optional[str]:
    """Best-effort 'App — Window title' for the frontmost window."""
    platform = platform or detect_platform()
    if platform == "macos":
        script = (
            'tell application "System Events" to set p to name of first application '
            "process whose frontmost is true\nreturn p"
        )
        app = _run(["osascript", "-e", script])
        return app
    if platform == "linux":
        name = _run(["xdotool", "getactivewindow", "getwindowname"])
        return name
    return None  # windows: skipped (best-effort)


def gather_context(now: Optional[datetime] = None, platform: Optional[str] = None) -> dict:
    """Collect a snapshot of the user's current situation."""
    now = now or datetime.now()
    platform = platform or detect_platform()
    ctx = {
        "time": now.strftime("%A %Y-%m-%d %H:%M"),
        "platform": platform,
    }
    win = active_window(platform)
    if win:
        ctx["active_app"] = win
    return ctx


def format_context(ctx: dict) -> str:
    """Render a context dict as the system-block text the brain injects (pure)."""
    lines = ["\n## Right now (ambient context — use it, don't recite it)"]
    if ctx.get("time"):
        lines.append(f"- Time: {ctx['time']}")
    if ctx.get("platform"):
        lines.append(f"- Machine: {ctx['platform']}")
    if ctx.get("active_app"):
        lines.append(f"- Foreground app: {ctx['active_app']}")
    return "\n".join(lines)
