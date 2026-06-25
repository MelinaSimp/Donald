"""Example tools + a default registry.

These are intentionally pure and non-throwing so the Tier 2 demo is stable.
Robust failure handling (errors-as-data at the boundary) is Tier 3's job, not
the tool's.
"""

from __future__ import annotations

import ast
import operator
from typing import Any

from .registry import Tool, ToolRegistry

# --- calculator --------------------------------------------------------------

_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
}
_UNARYOPS = {ast.UAdd: operator.pos, ast.USub: operator.neg}


def _safe_eval(node: ast.AST) -> float:
    """Evaluate an arithmetic AST node — no names, calls, or attribute access."""
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _BINOPS:
        return _BINOPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _UNARYOPS:
        return _UNARYOPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("unsupported expression")


def _calculator(inp: dict[str, Any]) -> str:
    expr = str(inp.get("expression", ""))
    value = _safe_eval(ast.parse(expr, mode="eval").body)
    return str(value)


CALCULATOR = Tool(
    name="calculator",
    description="Evaluate a basic arithmetic expression (+, -, *, /, **, %).",
    input_schema={
        "type": "object",
        "properties": {
            "expression": {
                "type": "string",
                "description": "Arithmetic expression, e.g. '2 * (3 + 4)'.",
            }
        },
        "required": ["expression"],
    },
    handler=_calculator,
)

# --- word_count --------------------------------------------------------------


def _word_count(inp: dict[str, Any]) -> str:
    text = str(inp.get("text", ""))
    return str(len(text.split()))


WORD_COUNT = Tool(
    name="word_count",
    description="Count the number of whitespace-separated words in some text.",
    input_schema={
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "The text to count words in."}
        },
        "required": ["text"],
    },
    handler=_word_count,
)


def build_default_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(CALCULATOR)
    registry.register(WORD_COUNT)
    return registry
