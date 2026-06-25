"""The heartbeat (Tier 5).

A lightweight background loop, separate from the conversation loop, that wakes on
an interval, runs a small set of scheduled checks, and routes anything noteworthy
into one place you'll see it. Quiet by default — it earns interruptions.

Hard-won rules, built in from the start:
  - Quiet by default: most checks produce nothing most of the time. A "calm"
    notice goes only to the inbox; a "loud" one may interrupt (print now).
  - Catch-up-on-return: every notice is held in the inbox, so nothing you weren't
    around to see is lost.
  - Quiet hours: a loud notice during quiet hours is held, not fired.
  - Survive restarts: each check's next-due time is persisted, so restarting
    doesn't reset every timer or fire everything at once.
  - No overlap: checks run sequentially in one tick, so a slow check can't stack.
  - Kill switch: while paused, the loop stays alive but runs no checks.
  - Dismissible: every surfaced item can be acknowledged and cleared.

Designed to not care which machine it's on — moving it to an always-on host
later is a relocation, not a rewrite.
"""
from __future__ import annotations

import time
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any, Callable

from .safety import is_paused
from .store import load_json, save_json


# --- the inbox: held, dismissible notices ----------------------------------
class Inbox:
    def __init__(self, path: Path):
        self.path = path

    def _all(self) -> list[dict[str, Any]]:
        return load_json(self.path, [])

    def _save(self, items: list[dict[str, Any]]) -> None:
        save_json(self.path, items)

    def add(self, text: str, level: str = "calm", kind: str = "note") -> dict[str, Any]:
        items = self._all()
        item = {
            "id": max((i["id"] for i in items), default=0) + 1,
            "ts": datetime.now().isoformat(timespec="seconds"),
            "text": text,
            "level": level,
            "kind": kind,
            "dismissed": False,
        }
        items.append(item)
        self._save(items)
        return item

    def pending(self) -> list[dict[str, Any]]:
        return [i for i in self._all() if not i["dismissed"]]

    def dismiss(self, item_id: int | None = None) -> int:
        items = self._all()
        n = 0
        for i in items:
            if not i["dismissed"] and (item_id is None or i["id"] == item_id):
                i["dismissed"] = True
                n += 1
        self._save(items)
        return n


# --- checks ----------------------------------------------------------------
class Check:
    def __init__(self, name: str, every_seconds: int, level: str,
                 fn: Callable[["HeartbeatContext"], list[str]]):
        self.name = name
        self.every_seconds = every_seconds
        self.level = level
        self.fn = fn


class HeartbeatContext:
    """Everything the checks need. Plain data — no LLM required for the baseline
    checks."""

    def __init__(self, config, reminders, inbox: Inbox, state: dict[str, Any]):
        self.config = config
        self.reminders = reminders
        self.inbox = inbox
        self.state = state  # free-form persisted scratch space for checks


def _check_due_reminders(ctx: HeartbeatContext) -> list[str]:
    """Surface reminders whose due time has passed, once each."""
    surfaced = set(ctx.state.setdefault("surfaced_reminders", []))
    out: list[str] = []
    now = datetime.now()
    for r in ctx.reminders.list():
        due = r.get("due")
        if not due or r["id"] in surfaced:
            continue
        try:
            if datetime.fromisoformat(due) <= now:
                out.append(f"Reminder due: {r['text']} (#{r['id']})")
                surfaced.add(r["id"])
        except ValueError:
            continue
    ctx.state["surfaced_reminders"] = sorted(surfaced)
    return out


def _check_pulse(ctx: HeartbeatContext) -> list[str]:
    return [f"Heartbeat alive at {datetime.now():%H:%M}."]


_BUILTIN_CHECKS = {
    "due_reminders": _check_due_reminders,
    "heartbeat_pulse": _check_pulse,
}


# --- the loop --------------------------------------------------------------
class Heartbeat:
    def __init__(self, config, reminders, inbox: Inbox, audit,
                 on_loud: Callable[[str], None] | None = None):
        self.config = config
        self.reminders = reminders
        self.inbox = inbox
        self.audit = audit
        self.on_loud = on_loud or (lambda msg: print(f"\n🔔 {msg}"))
        self.state_path = config.resolve_path("heartbeat.state_path", "data/heartbeat_state.json")
        self.state = load_json(self.state_path, {"next_due": {}, "checks": {}})
        self.checks = self._build_checks()

    def _build_checks(self) -> list[Check]:
        checks = []
        for c in self.config.get("heartbeat.checks", []):
            fn = _BUILTIN_CHECKS.get(c["name"])
            if fn is None:
                continue
            checks.append(Check(c["name"], int(c["every_seconds"]), c.get("level", "calm"), fn))
        return checks

    def _persist(self) -> None:
        save_json(self.state_path, self.state)

    def _in_quiet_hours(self, now: datetime | None = None) -> bool:
        start = self._parse_time(self.config.get("heartbeat.quiet_hours.start", "22:00"))
        end = self._parse_time(self.config.get("heartbeat.quiet_hours.end", "08:00"))
        t = (now or datetime.now()).time()
        if start <= end:
            return start <= t < end
        return t >= start or t < end  # window wraps midnight

    @staticmethod
    def _parse_time(s: str) -> dtime:
        h, m = (int(x) for x in s.split(":"))
        return dtime(h, m)

    def tick(self) -> None:
        """One pass: run any due checks, surface results. Safe to call on a
        timer; resumes from persisted schedule."""
        if is_paused(self.config):
            return  # kill switch: hold all background work, loop stays alive
        now = time.time()
        due_times: dict[str, float] = self.state.setdefault("next_due", {})
        check_state: dict[str, Any] = self.state.setdefault("checks", {})
        for check in self.checks:
            # New checks (no persisted state) fire on this first tick. On a
            # *restart* the persisted next_due governs, so we never refire a
            # backlog — and per-check surfaced-tracking stops duplicate notices.
            next_due = due_times.get(check.name, now)
            if now < next_due:
                continue
            ctx = HeartbeatContext(self.config, self.reminders, self.inbox,
                                   check_state.setdefault(check.name, {}))
            try:
                notices = check.fn(ctx) or []
            except Exception as e:  # noqa: BLE001
                self.audit("check_error", check=check.name, error=str(e))
                notices = []
            for text in notices:
                self.inbox.add(text, level=check.level, kind=check.name)
                self.audit("surfaced", check=check.name, level=check.level, text=text)
                if check.level == "loud" and not self._in_quiet_hours():
                    self.on_loud(text)  # interrupt now; otherwise it waits in the inbox
            due_times[check.name] = now + check.every_seconds
        self._persist()

    def run_forever(self) -> None:
        tick_seconds = int(self.config.get("heartbeat.tick_seconds", 60))
        print(f"💓 Heartbeat running (tick {tick_seconds}s). Ctrl-C to stop.")
        try:
            while True:
                self.tick()
                time.sleep(tick_seconds)
        except KeyboardInterrupt:
            print("\nHeartbeat stopped.")
