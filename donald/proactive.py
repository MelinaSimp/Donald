"""Proactivity — Donald speaks first.

A reactive assistant only talks when you talk to it. Jarvis talks *first*:
"Sir, you have a meeting in ten minutes." This engine is the seed of that. It
runs a background loop and, when something is due, pushes a spoken line out
through a sink (the app's outbound queue → the UI speaks it) without you asking.

The first watcher is reminders: say "Donald, remind me in ten minutes to call
Luca," and ten minutes later he brings it up on his own. New proactive triggers
(calendar, a failing build, a file changing) plug in the same way — schedule a
message, the loop delivers it.

The scheduling/eligibility logic is pure (:meth:`due` takes the current time and
returns what to say), so it's tested without threads or a clock; only the
background loop needs real time.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional


@dataclass(order=True)
class _Reminder:
    due_at: float
    message: str = field(compare=False)


class ProactiveEngine:
    """Background loop that delivers due proactive messages through a sink.

    Parameters
    ----------
    sink:
        Called with each spoken line when it's due (the app enqueues it for the
        UI to speak).
    kill_switch:
        Optional object with an ``.active`` property; while active, nothing is
        delivered (messages are held, not dropped, and go out once resumed).
    interval:
        Seconds between ticks of the background loop.
    """

    def __init__(
        self,
        sink: Callable[[str], None],
        kill_switch=None,
        interval: float = 1.0,
    ) -> None:
        self._sink = sink
        self._kill_switch = kill_switch
        self._interval = interval
        self._reminders: List[_Reminder] = []
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def set_sink(self, sink: Callable[[str], None]) -> None:
        """Point proactive output at a delivery callback (e.g. the UI queue)."""
        self._sink = sink

    # -- scheduling (pure-ish; time injected for tests) -------------------
    def schedule(self, due_at: float, message: str) -> None:
        with self._lock:
            self._reminders.append(_Reminder(due_at, message))

    def add_reminder(self, delay_s: float, message: str) -> None:
        """Schedule a reminder ``delay_s`` seconds from now."""
        self.schedule(time.monotonic() + max(0.0, delay_s), message)

    def due(self, now: float) -> List[str]:
        """Pop and return the spoken lines due at/before ``now``.

        Held (returned empty) while the kill switch is active, so a paused
        Donald stays silent but doesn't lose the reminder.
        """
        if self._kill_switch is not None and self._kill_switch.active:
            return []
        with self._lock:
            due, keep = [], []
            for r in self._reminders:
                (due if r.due_at <= now else keep).append(r)
            self._reminders = keep
        return [self._phrase(r.message) for r in due]

    @staticmethod
    def _phrase(message: str) -> str:
        return f"Hey Champ — you told me to remind you: {message}. Consider it handled."

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._reminders)

    # -- background loop --------------------------------------------------
    def _run(self) -> None:
        while not self._stop.wait(self._interval):
            for line in self.due(time.monotonic()):
                try:
                    self._sink(line)
                except Exception:
                    pass

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
