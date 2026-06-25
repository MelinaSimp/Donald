"""3.2 - Per-tool anomaly detection (sliding-window safety caps).

Threat T7 (tool-frequency abuse): a runaway loop sending 200 emails in 10
minutes, or a compromised cron firing the destructive tool repeatedly.
``AnomalyGate`` keeps an in-memory sliding window per tool and blocks a call
that would exceed the tool's cap.

    gate = AnomalyGate()                      # uses DEFAULT_CAPS
    res = gate.check_and_record("send_email")
    if res["status"] == "anomaly_gate_blocked":
        return res                            # surface count/limit/window to the LLM
    ... actually send the email ...

A blocked call is NOT recorded, so the cap is a true ceiling (a sliding
window), not one-strike-and-disabled.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, Optional, Tuple

# tool_name -> (limit, window_seconds). Tune to your use case. Glob-ish
# prefixes are matched longest-first via resolve_cap() (e.g. "delete_").
DEFAULT_CAPS: Dict[str, Tuple[int, float]] = {
    "send_email": (5, 3600),         # 5/hour -- catch an inbox-runaway early
    "send_message": (5, 3600),
    "delete_": (3, 86400),           # any delete_* tool: 3/day
    "forget_": (3, 86400),
    "execute_code": (20, 86400),
    "run_code": (20, 86400),
    "write_file": (30, 3600),
    "transfer": (2, 86400),          # money movement: single digits/day
    "refund": (3, 86400),
}


class AnomalyGate:
    """Sliding-window per-tool rate caps. Thread-safe, in-process."""

    def __init__(
        self,
        caps: Optional[Dict[str, Tuple[int, float]]] = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.caps = dict(DEFAULT_CAPS if caps is None else caps)
        self._clock = clock
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def resolve_cap(self, tool: str) -> Optional[Tuple[str, int, float]]:
        """Find the cap governing ``tool``: exact match, else longest prefix.

        Returns ``(cap_key, limit, window_seconds)`` or ``None`` if uncapped.
        """
        if tool in self.caps:
            limit, window = self.caps[tool]
            return tool, limit, window
        best: Optional[str] = None
        for key in self.caps:
            if key.endswith("_") and tool.startswith(key):
                if best is None or len(key) > len(best):
                    best = key
        if best is not None:
            limit, window = self.caps[best]
            return best, limit, window
        return None

    def check_and_record(self, tool: str) -> Dict[str, object]:
        """Record a call if under cap; otherwise block (without recording)."""
        resolved = self.resolve_cap(tool)
        if resolved is None:
            return {"status": "ok", "tool": tool, "uncapped": True}

        cap_key, limit, window = resolved
        now = self._clock()
        with self._lock:
            dq = self._hits[cap_key]
            cutoff = now - window
            while dq and dq[0] < cutoff:
                dq.popleft()
            if len(dq) >= limit:
                return {
                    "status": "anomaly_gate_blocked",
                    "tool": tool,
                    "cap_key": cap_key,
                    "count": len(dq),
                    "limit": limit,
                    "window_seconds": window,
                    "message": (
                        f"{tool} hit its safety cap ({limit} per {int(window)}s). "
                        "Blocked to prevent a runaway loop; not recorded."
                    ),
                }
            dq.append(now)
            return {
                "status": "ok",
                "tool": tool,
                "cap_key": cap_key,
                "count": len(dq),
                "limit": limit,
                "window_seconds": window,
            }

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
