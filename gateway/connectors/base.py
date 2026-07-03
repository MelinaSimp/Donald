"""The connector contract.

A connector is anything Donald can hand a natural-language task to and get a
result back. Keeping this a tiny ``Protocol`` is the whole point: Hermes is the
first implementation, but the orchestrator only depends on this shape, so a
different local agent (or a mock, in tests) slots in unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable


class ConnectorError(RuntimeError):
    """Raised when a connector cannot reach or complete a task."""


@dataclass
class ConnectorResult:
    """The outcome of delegating one task to a connector."""

    ok: bool
    text: str
    connector: str
    error: Optional[str] = None
    raw: Optional[dict] = None


@runtime_checkable
class AgentConnector(Protocol):
    """Minimal interface the orchestrator relies on."""

    name: str

    async def health(self) -> bool:
        """Return True if the underlying agent is reachable."""
        ...

    async def execute(self, task: str, *, context: Optional[str] = None) -> ConnectorResult:
        """Run one task to completion and return the result.

        A connector that can surface live progress may additionally accept an
        ``on_line`` keyword (called with each output line as it happens) and
        advertise it with a class attribute ``supports_streaming = True`` —
        the orchestrator only passes ``on_line`` when that flag is present.
        """
        ...

    async def aclose(self) -> None:
        """Release any held resources (HTTP clients, sockets)."""
        ...
