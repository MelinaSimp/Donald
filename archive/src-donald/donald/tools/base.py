"""Base interface shared by every Donald tool."""

from __future__ import annotations

from typing import Any


class BaseTool:
    """Base class for all tools Donald can call.

    A tool advertises a stable :attr:`name`, a human-readable
    :attr:`description`, and a :attr:`category` used to group it in the
    self-knowledge document. Subclasses implement :meth:`execute`.
    """

    name: str = ""
    description: str = ""
    category: str = "general"

    def execute(self, **kwargs: Any) -> Any:  # pragma: no cover - interface
        raise NotImplementedError

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<{type(self).__name__} name={self.name!r}>"
