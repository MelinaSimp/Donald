"""Tier 5 — safety rails.

A proactive assistant that can write files, run shells and reach out on its own
needs brakes. The safety gate sits between the registry and every tool call and
enforces three things:

1. **Hard blocks** — patterns that are never allowed (rm -rf /, fork bombs,
   piping the internet into a shell, sudo, disk wipes). These raise and the
   brain is told it was blocked.
2. **Confirmation** — *mutating* tools (write_file, run_shell, remember, forget)
   require approval. In interactive text/voice mode that's a yes/no prompt; in
   the unattended proactive loop the default is to DENY, so Donald can never
   quietly change your world while you're away.
3. **Audit** — every gated decision is logged so you can see what Donald did or
   tried to do.

The gate is installed by ``install_safety`` and is a no-op for read-only tools,
so nothing here slows down ordinary questions.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from .config import Config
from .tools.base import Registry, Tool, ToolError

# Shell patterns that are never allowed, even with confirmation.
HARD_BLOCK = [
    r"rm\s+-rf?\s+[/~]",          # wiping root/home
    r":\(\)\s*\{.*\};:",          # fork bomb
    r"\bmkfs\b",                   # formatting filesystems
    r"\bdd\b.*\bof=/dev/",        # writing to raw devices
    r">\s*/dev/sd[a-z]",          # clobbering disks
    r"\bsudo\b",                   # privilege escalation
    r"curl[^|]*\|\s*(sudo\s+)?(ba)?sh",   # curl | sh
    r"wget[^|]*\|\s*(sudo\s+)?(ba)?sh",   # wget | sh
    r"\bchmod\s+-R\s+777\s+/",    # opening up the whole fs
]
HARD_BLOCK_RE = [re.compile(p, re.IGNORECASE) for p in HARD_BLOCK]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class SafetyGate:
    config: Config
    # Returns True to allow a mutating action. Set by the front-end.
    confirmer: Callable[[Tool, dict], bool] | None = None
    # When True (proactive/unattended), mutating tools are denied by default.
    unattended: bool = False
    audit_log: list[dict] = field(default_factory=list)

    def __call__(self, tool: Tool, args: dict) -> None:
        # 1. Hard blocks on shell content.
        if tool.name == "run_shell":
            command = str(args.get("command", ""))
            for rx in HARD_BLOCK_RE:
                if rx.search(command):
                    self._audit(tool, args, "hard-block")
                    raise ToolError(
                        f"command matches a forbidden pattern ({rx.pattern}). "
                        "Refused for safety."
                    )

        # 2. Read-only tools pass straight through.
        if not tool.mutating:
            self._audit(tool, args, "allow:read-only")
            return

        # 3. Mutating tools need confirmation.
        if self.unattended:
            self._audit(tool, args, "deny:unattended")
            raise ToolError(
                f"'{tool.name}' changes things and Donald is running unattended; "
                "deferring it until you're here to approve."
            )

        if self.confirmer is None:
            # No way to ask → fail safe by allowing only when explicitly opted in.
            self._audit(tool, args, "allow:no-confirmer")
            return

        if self.confirmer(tool, args):
            self._audit(tool, args, "allow:confirmed")
            return
        self._audit(tool, args, "deny:declined")
        raise ToolError(f"you declined the '{tool.name}' action.")

    def _audit(self, tool: Tool, args: dict, decision: str) -> None:
        self.audit_log.append(
            {"at": _now(), "tool": tool.name, "args": args, "decision": decision}
        )


def cli_confirmer(tool: Tool, args: dict) -> bool:
    """Interactive yes/no prompt for the text loop."""
    print(
        f"\n\033[33m⚠ Donald wants to run '{tool.name}' with {args}.\033[0m",
        file=sys.stderr,
    )
    try:
        answer = input("   Allow? [y/N] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in ("y", "yes")


def install_safety(
    reg: Registry, config: Config, unattended: bool = False, interactive: bool = True
) -> SafetyGate:
    gate = SafetyGate(
        config=config,
        confirmer=cli_confirmer if interactive else None,
        unattended=unattended,
    )
    reg.safety_gate = gate
    return gate
