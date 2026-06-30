"""A small starter tool catalog.

These exist so the Factory has real tools to allowlist and spawned agents
have something to call. The set deliberately includes tools marked
``factory_allowed=False`` (``read_env``, ``send_email``) to demonstrate the
internal-only opt-out: those are secrets-bearing / outward-facing and must
never be handed to a spawned agent.

Replace/extend this with your real host catalog.
"""

from __future__ import annotations

import ast
import datetime as _dt
import operator
from typing import Any, Optional

from agent_factory.search import NullSearchBackend, SearchBackend
from agent_factory.tools.registry import Tool, ToolRegistry

# --- safe arithmetic for the calculator tool ------------------------------- #

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}
_ALLOWED_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _safe_eval(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY:
        return _ALLOWED_UNARY[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression")


def _calculator(args: dict[str, Any]) -> str:
    expr = str(args.get("expression", ""))
    try:
        return str(_safe_eval(ast.parse(expr, mode="eval")))
    except Exception as exc:  # noqa: BLE001 - report to the model, don't crash
        return f"error: {exc}"


def _current_time(_args: dict[str, Any]) -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def build_default_registry(search_backend: Optional[SearchBackend] = None) -> ToolRegistry:
    """Construct a registry seeded with the starter catalog."""
    backend = search_backend or NullSearchBackend()
    reg = ToolRegistry()

    reg.register(
        Tool(
            name="web_search",
            description="Search the web for up-to-date information. Returns a list of results with url, title, and snippet.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Search query"}},
                "required": ["query"],
            },
            execute=lambda a: backend.search(str(a.get("query", ""))),
            factory_allowed=True,
        )
    )
    reg.register(
        Tool(
            name="calculator",
            description="Evaluate a basic arithmetic expression (e.g. '2 * (3 + 4)').",
            input_schema={
                "type": "object",
                "properties": {"expression": {"type": "string"}},
                "required": ["expression"],
            },
            execute=_calculator,
            factory_allowed=True,
        )
    )
    reg.register(
        Tool(
            name="current_time",
            description="Return the current UTC time in ISO-8601 format.",
            input_schema={"type": "object", "properties": {}},
            execute=_current_time,
            factory_allowed=True,
        )
    )

    # --- internal-only: NEVER handed to spawned agents --------------------- #
    reg.register(
        Tool(
            name="read_env",
            description="[internal] Read a host environment variable.",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            execute=lambda a: "(redacted — internal tool)",
            factory_allowed=False,
        )
    )
    reg.register(
        Tool(
            name="send_email",
            description="[internal] Send an email via the host mail service.",
            input_schema={
                "type": "object",
                "properties": {
                    "to": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                },
                "required": ["to", "subject", "body"],
            },
            execute=lambda a: "(disabled — internal tool)",
            factory_allowed=False,
        )
    )
    return reg
