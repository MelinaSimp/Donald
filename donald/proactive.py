"""Tier 4 — the always-on background loop that lets Donald reach out first.

Most of the time Donald answers when spoken to. This loop is the other half:
on an interval it checks a set of *triggers* (due reminders today; easy to add
more — calendar gaps, unread-since, daily briefing) and, when one fires, hands a
message to a ``notifier`` so it surfaces to you.

Two safety properties are baked in, not bolted on:

* The loop runs an agent whose safety gate is in **unattended** mode, so the
  brain can read/think but cannot write files, run shells, or otherwise change
  your world while you're not there to approve (Tier 5).
* Triggers fire at most once (reminders are marked fired) so Donald doesn't
  nag in a loop.

The check logic is a plain method you can call in a test; the thread is just a
timer around it.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Callable, Protocol

from .memory import Memory


class Trigger(Protocol):
    """A thing worth interrupting the user about. Returns messages to send."""

    def __call__(self, memory: Memory) -> list[str]:
        ...


def reminder_trigger(memory: Memory) -> list[str]:
    """Surface any reminders that have come due, once each."""
    messages: list[str] = []
    for rem in memory.due_reminders():
        memory.mark_fired(rem.id)
        messages.append(f"Reminder: {rem.text}")
    return messages


@dataclass
class ProactiveLoop:
    memory: Memory
    notifier: Callable[[str], None]
    interval: int = 60
    triggers: list[Trigger] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.triggers is None:
            self.triggers = [reminder_trigger]
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    # -- the testable core ------------------------------------------------
    def check(self) -> list[str]:
        """Run every trigger once and return the messages produced."""
        out: list[str] = []
        for trig in self.triggers:
            try:
                out.extend(trig(self.memory))
            except Exception as exc:  # a broken trigger must not kill the loop
                out.append(f"(a background check failed: {exc})")
        return out

    def tick(self) -> None:
        for message in self.check():
            self.notifier(message)

    # -- the timer wrapper ------------------------------------------------
    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self.interval)

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
