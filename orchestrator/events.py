"""Observer hooks — the fire-and-forget side of Tier 3.

Anything that emits events to a UI, log stream, or analytics sink is an
observer. Observers must never be able to break real work: if a hook throws,
we swallow it and log, so a broken dashboard can't block a dispatch.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger("orchestrator")

# An observer receives an event name and a payload dict. Its return value is
# ignored; its exceptions are contained.
Observer = Callable[[str, dict[str, Any]], None]


class EventEmitter:
    """Fan an event out to every observer, isolating each one's failures."""

    def __init__(self, observers: list[Observer] | None = None) -> None:
        self._observers: list[Observer] = list(observers or [])

    def subscribe(self, observer: Observer) -> None:
        self._observers.append(observer)

    def emit(self, event: str, **payload: Any) -> None:
        for observer in self._observers:
            try:
                observer(event, payload)
            except Exception as exc:  # noqa: BLE001 — containment is the point
                # A broken observer must never propagate into the work path.
                logger.warning("observer hook failed on %r: %s", event, exc)
