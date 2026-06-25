"""Concrete tools shipped with Donald."""

from __future__ import annotations

from typing import Any, Dict, List

from .base import BaseTool


class EchoTool(BaseTool):
    name = "echo"
    description = "Return the text it was given, unchanged."
    category = "utility"

    def execute(self, text: str = "", **_: Any) -> str:
        return text


class CalculatorTool(BaseTool):
    name = "calculator"
    description = "Evaluate a basic arithmetic expression and return the result."
    category = "utility"

    _ALLOWED = set("0123456789.+-*/() ")

    def execute(self, expression: str = "", **_: Any) -> float:
        if not set(expression) <= self._ALLOWED:
            raise ValueError("expression contains disallowed characters")
        return float(eval(expression, {"__builtins__": {}}, {}))  # noqa: S307


class WebSearchTool(BaseTool):
    name = "web_search"
    description = "Search the web and return ranked result snippets."
    category = "research"

    def execute(self, query: str = "", **_: Any) -> List[Dict[str, str]]:
        # Placeholder: wired to a real backend via the Tavily integration.
        return []


class SendEmailTool(BaseTool):
    name = "send_email"
    description = "Compose and send an email via the configured mail provider."
    category = "communication"

    def execute(self, to: str = "", subject: str = "", body: str = "", **_: Any) -> Dict[str, Any]:
        # Placeholder: wired to a real backend via the SMTP integration.
        return {"queued": True, "to": to, "subject": subject}
