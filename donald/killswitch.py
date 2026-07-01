"""Runtime kill switch — one word halts Donald.

Before you let an assistant listen all day and click anything on screen, you
need a hard stop you can hit instantly, by voice or by button. This is that
stop. When engaged, every Hermes action refuses and every spoken turn short-
circuits to "I'm on hold" — nothing runs until you resume.

It layers on the repo's env-var switch (:mod:`security.killswitch`): the env var
is the ops/incident lever (flip it in a secrets manager), while this runtime
flag is the in-session lever you toggle from the UI or by saying "stop". Either
being active means paused.
"""

from __future__ import annotations

import threading

from security.killswitch import is_active as _env_active

# Phrases the UI catches locally to engage/release without going through the
# model — a stop word must never wait on an API call.
STOP_PHRASES = ("stop", "freeze", "kill switch", "halt", "abort", "shut it down")
RESUME_PHRASES = ("resume", "wake up", "you're back", "unfreeze", "carry on", "go ahead")


class KillSwitch:
    """Thread-safe runtime pause flag that also honors the env-var switch."""

    def __init__(self) -> None:
        self._engaged = False
        self._lock = threading.Lock()

    def engage(self) -> None:
        with self._lock:
            self._engaged = True

    def release(self) -> None:
        with self._lock:
            self._engaged = False

    @property
    def active(self) -> bool:
        """True if paused by either the runtime flag or the env-var switch."""
        with self._lock:
            return self._engaged or _env_active()

    def paused_reply(self) -> str:
        return "I'm on hold, Champ. Say \"resume\" when you want me back — and I always come back big."


# One shared switch for the process (the app wires Hermes + brain + UI to it).
GLOBAL = KillSwitch()
