"""Hermes — Donald's hands on the computer.

Donald is the voice and the brain; **Hermes is the execution engine** that
actually touches the machine. Donald's reasoning loop decides *what* to do and
calls Hermes tools; Hermes carries the action out on the local OS and reports
back a plain-data result.

Design rules
------------
* **OS-aware, not OS-locked.** One ``Hermes`` instance detects the platform
  once and routes each action through the right adapter (macOS / Linux /
  Windows). Adding computer-use (screenshot + click) later means adding an
  adapter, not rewriting callers.
* **Safety is wired in, not bolted on.** Every shell command flows through the
  repo's :class:`security.approval.ApprovalGate` before it runs. The hardline
  blocklist (``rm -rf /``, fork bombs, disk wipes…) cannot be reasoned around,
  even by an injected instruction riding in on a voice transcript.
* **Least privilege at the spawn site.** Subprocesses inherit only the OS
  baseline env (``security.subprocess_env.shell_minimal``) — never the
  Anthropic key or other secrets.
* **Plain data out.** Every method returns an :class:`ActionResult` so the
  brain can narrate the outcome in Donald's voice and the UI can show it.
"""

from __future__ import annotations

import shlex
import subprocess
import sys
import webbrowser
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional

from security.approval import ApprovalGate
from security.log_redact import redact
from security.subprocess_env import shell_minimal

# Hermes never lets a single action hang the whole assistant.
_DEFAULT_TIMEOUT = 30


def detect_platform() -> str:
    """Return ``"macos"``, ``"windows"``, or ``"linux"`` for the host OS."""
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("win"):
        return "windows"
    return "linux"


@dataclass
class ActionResult:
    """The outcome of one Hermes action — plain data for brain + UI."""

    ok: bool
    action: str
    summary: str
    detail: str = ""
    needs_confirmation: bool = False
    confirm_token: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Hermes:
    """The computer-control engine behind Donald.

    Parameters
    ----------
    approval:
        Gate every shell command runs through. Defaults to ``smart`` mode —
        low-risk commands run, risky ones come back as ``needs_confirmation``
        so Donald asks the user out loud before doing anything destructive.
    dry_run:
        When ``True``, Hermes describes what it *would* do without executing.
        Useful for demos, tests, and the first run on a new machine.
    platform:
        Override the detected OS (mainly for tests).
    """

    approval: ApprovalGate = field(default_factory=lambda: ApprovalGate(mode="smart"))
    dry_run: bool = False
    platform: str = field(default_factory=detect_platform)
    # Computer-use (see/click/type any app) is powerful and opt-in — off here.
    enable_computer_use: bool = False
    # Pending confirmations: token -> the thunk that runs the approved command.
    _pending: dict = field(default_factory=dict, repr=False)
    _counter: int = field(default=0, repr=False)
    _computer: object = field(default=None, repr=False)

    # -- shell -------------------------------------------------------------
    def run_shell(self, command: str, confirmed: bool = False) -> ActionResult:
        """Run a shell command on the host, gated by the approval layer.

        Returns an ``ActionResult``. If the command is risky and not yet
        confirmed, ``needs_confirmation`` is set and a ``confirm_token`` is
        issued; call :meth:`confirm` with that token to actually run it.
        """
        command = (command or "").strip()
        if not command:
            return ActionResult(False, "run_shell", "Nothing to run — empty command.")

        decision = self.approval.evaluate(command, confirmed=confirmed)
        if decision.confirmation_required:
            token = self._stash(lambda: self._exec_shell(command))
            return ActionResult(
                ok=False,
                action="run_shell",
                summary=f"That one's {decision.risk}-risk ({decision.matched_rule}). "
                "Say the word and I'll run it.",
                detail=command,
                needs_confirmation=True,
                confirm_token=token,
            )
        if not decision.allowed:
            return ActionResult(
                ok=False,
                action="run_shell",
                summary=f"Not happening — {decision.reason}",
                detail=command,
            )
        return self._exec_shell(command)

    def _exec_shell(self, command: str) -> ActionResult:
        if self.dry_run:
            return ActionResult(True, "run_shell", f"[dry-run] would run: {command}", command)
        try:
            proc = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=_DEFAULT_TIMEOUT,
                env=shell_minimal(),  # no secrets leak into the child
            )
        except subprocess.TimeoutExpired:
            return ActionResult(False, "run_shell", f"Command timed out after {_DEFAULT_TIMEOUT}s.", command)
        except Exception as exc:  # pragma: no cover - defensive
            return ActionResult(False, "run_shell", f"Couldn't run it: {redact(str(exc))}", command)

        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        if proc.returncode == 0:
            return ActionResult(True, "run_shell", "Done.", redact(out) or "(no output)")
        return ActionResult(
            False,
            "run_shell",
            f"Exited {proc.returncode}.",
            redact(err or out) or "(no output)",
        )

    # -- apps & urls -------------------------------------------------------
    def open_app(self, name: str, confirmed: bool = False) -> ActionResult:
        """Launch a desktop application by name, per-OS."""
        name = (name or "").strip()
        if not name:
            return ActionResult(False, "open_app", "Which app? You didn't say.")
        if self.platform == "macos":
            cmd = f"open -a {shlex.quote(name)}"
        elif self.platform == "windows":
            cmd = f'start "" {shlex.quote(name)}'
        else:  # linux
            # gtk-launch wants a .desktop id; fall back to the bare binary name.
            cmd = f"gtk-launch {shlex.quote(name)} || {shlex.quote(name)} &"
        result = self.run_shell(cmd, confirmed=confirmed)
        if result.ok:
            result.action = "open_app"
            result.summary = f"Opening {name}. You're welcome."
        return result

    def open_url(self, url: str) -> ActionResult:
        """Open a URL in the default browser (no shell, no gate needed)."""
        url = (url or "").strip()
        if not url:
            return ActionResult(False, "open_url", "Give me a URL.")
        if "://" not in url:
            url = "https://" + url
        if self.dry_run:
            return ActionResult(True, "open_url", f"[dry-run] would open {url}", url)
        try:
            webbrowser.open(url)
        except Exception as exc:  # pragma: no cover - defensive
            return ActionResult(False, "open_url", f"Browser wouldn't open: {redact(str(exc))}", url)
        return ActionResult(True, "open_url", f"Pulling up {url}.", url)

    # -- computer-use (see/click/type any app) ----------------------------
    @property
    def computer(self):
        """Lazily build the computer-use controller (shares dry_run)."""
        if self._computer is None:
            from .computer import ComputerController

            self._computer = ComputerController(dry_run=self.dry_run)
        return self._computer

    def computer_action(self, action: str, **params):
        """Execute one computer-use action; returns a ``ComputerResult``."""
        return self.computer.execute(action, **params)

    # -- confirmation handshake -------------------------------------------
    def _stash(self, thunk: Callable[[], ActionResult]) -> str:
        self._counter += 1
        token = f"hermes-confirm-{self._counter}"
        self._pending[token] = thunk
        return token

    def confirm(self, token: str) -> ActionResult:
        """Run a previously gated command the user just approved out loud."""
        thunk = self._pending.pop(token, None)
        if thunk is None:
            return ActionResult(False, "confirm", "That approval expired — ask me again.")
        return thunk()

    def cancel(self, token: str) -> ActionResult:
        """Drop a pending confirmation the user declined."""
        existed = self._pending.pop(token, None) is not None
        return ActionResult(
            existed, "cancel", "Forget it then." if existed else "Nothing pending to cancel."
        )
