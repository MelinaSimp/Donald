"""Tier 1 tools — explicit memory writes/reads (backed by Tier 3 SQLite)."""

from __future__ import annotations

from ..memory import Memory
from .base import Registry, Tool, ToolError


def register(reg: Registry) -> None:
    reg.register(
        Tool(
            name="remember",
            description=(
                "Save a durable fact about the user that should persist across "
                "restarts (preferences, names, context). Use whenever the user "
                "says 'remember…' or tells you something worth keeping."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The fact to store."},
                    "category": {
                        "type": "string",
                        "description": "Optional grouping, e.g. 'food', 'work'.",
                    },
                },
                "required": ["content"],
            },
            func=remember,
            mutating=True,
        )
    )
    reg.register(
        Tool(
            name="recall",
            description="Search remembered facts for anything matching a query.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
            func=recall,
        )
    )
    reg.register(
        Tool(
            name="list_memories",
            description="List everything Donald currently remembers about the user.",
            input_schema={"type": "object", "properties": {}},
            func=list_memories,
        )
    )
    reg.register(
        Tool(
            name="forget",
            description="Delete a remembered fact by its id (from list_memories).",
            input_schema={
                "type": "object",
                "properties": {"fact_id": {"type": "integer"}},
                "required": ["fact_id"],
            },
            func=forget,
            mutating=True,
        )
    )


def remember(content: str, ctx, category: str = "general") -> str:
    memory: Memory = ctx.memory
    fact = memory.add_fact(content, category)
    return f"Remembered (#{fact.id}): {fact.content}"


def recall(query: str, ctx) -> str:
    memory: Memory = ctx.memory
    facts = memory.search_facts(query)
    if not facts:
        return f"Nothing remembered about '{query}'."
    return "\n".join(f"#{f.id} [{f.category}] {f.content}" for f in facts)


def list_memories(ctx) -> str:
    memory: Memory = ctx.memory
    facts = memory.list_facts()
    if not facts:
        return "I don't have any saved memories yet."
    return "\n".join(f"#{f.id} [{f.category}] {f.content}" for f in facts)


def forget(fact_id: int, ctx) -> str:
    memory: Memory = ctx.memory
    if memory.forget_fact(int(fact_id)):
        return f"Forgot fact #{fact_id}."
    raise ToolError(f"No fact #{fact_id} to forget.")
