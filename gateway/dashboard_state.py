"""Dashboard state tracking — logs actions and system status for the control panel."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional


@dataclass
class DashboardAction:
    """One action logged by Hermes."""

    timestamp: float
    action_type: str  # "tool_call", "tool_result", "text", "voice", etc.
    name: str  # "hermes", "text", "voice"
    status: str  # "pending", "ok", "error", "declined"
    task: Optional[str] = None
    reason: Optional[str] = None
    preview: Optional[str] = None  # preview of result
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class DashboardState:
    """Mutable store for dashboard data."""

    def __init__(self, max_actions: int = 100):
        self.max_actions = max_actions
        self.actions: deque = deque(maxlen=max_actions)
        self.session_turn_count = 0
        self.hermes_action_count = 0
        self.last_session_id: Optional[str] = None
        self.last_user_message: Optional[str] = None
        self.last_response: Optional[str] = None
        self._lock_time = 0.0
        self._paused = False

    def record_event(self, session_id: str, event: Dict[str, Any]) -> None:
        """Log a turn event."""
        event_type = event.get("type")

        if event_type == "tool_call":
            self.hermes_action_count += 1
            action = DashboardAction(
                timestamp=time.time(),
                action_type="tool_call",
                name="hermes",
                status="pending",
                task=event.get("task"),
                reason=event.get("reason"),
            )
            self.actions.append(action)
        elif event_type == "tool_result":
            if self.actions and self.actions[-1].action_type == "tool_call":
                last = self.actions[-1]
                last.status = "error" if event.get("error") else "ok"
                if event.get("declined"):
                    last.status = "declined"
                last.error = event.get("error")
                last.preview = event.get("preview")
        elif event_type == "delta":
            if self.actions and self.actions[-1].action_type == "tool_result":
                # Text delta after a tool result
                pass
        elif event_type == "final":
            self.session_turn_count += 1
            self.last_response = event.get("text")
            self.last_session_id = session_id

    def set_user_message(self, message: str) -> None:
        """Track user input."""
        self.last_user_message = message

    def pause(self) -> None:
        """Pause execution (simulating a kill switch)."""
        self._paused = True
        self._lock_time = time.time()

    def resume(self) -> None:
        """Resume execution."""
        self._paused = False

    @property
    def is_paused(self) -> bool:
        return self._paused

    def snapshot(self) -> Dict[str, Any]:
        """Return a JSON-serializable snapshot."""
        return {
            "paused": self._paused,
            "turn_count": self.session_turn_count,
            "hermes_actions": self.hermes_action_count,
            "last_session_id": self.last_session_id,
            "last_user_message": self.last_user_message,
            "last_response": self.last_response,
            "actions": [a.to_dict() for a in reversed(list(self.actions))],  # newest first
        }


# Global state instance.
_dashboard_state: Optional[DashboardState] = None


def get_dashboard_state() -> DashboardState:
    """Get or create the global dashboard state."""
    global _dashboard_state
    if _dashboard_state is None:
        _dashboard_state = DashboardState()
    return _dashboard_state
