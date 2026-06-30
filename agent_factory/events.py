"""Event sink for pipeline transitions and registry changes.

Every state transition and the final ``agent_added`` are emitted here. For
the CLI surface this just logs; a web surface would swap in a WebSocket
broadcast. The ``agent_added`` event carries ``created_by_task_id`` so a
list-based approval UI can clear the right pending row on resolution.
"""

from __future__ import annotations

from typing import Any, Callable, Protocol


class EventSink(Protocol):
    def __call__(self, *, kind: str, event: dict[str, Any]) -> None: ...


class LoggingEventSink:
    def __init__(self, verbose: bool = True) -> None:
        self.verbose = verbose
        self.events: list[dict] = []

    def __call__(self, *, kind: str, event: dict[str, Any]) -> None:
        self.events.append({"kind": kind, **event})
        if self.verbose:
            print(f"[event] {kind}: {event}")


def null_sink(*, kind: str, event: dict[str, Any]) -> None:  # noqa: D401
    """An event sink that drops everything (used in tests)."""
    return None
