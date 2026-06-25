"""Consequential tools (Tier 6) — the "never without asking" list.

Every tool here is marked consequential=True, so the agent's confirmation gate
stops and gets the user's explicit yes before it runs — for typed, spoken, and
heartbeat-initiated calls alike.

draft_message is the safe counterpart to send_message: drafting is free, sending
asks first (the interview's fourth capability, gated as designed).

In this baseline these mostly simulate the side effect and log it — wiring them
to a real email provider, payment API, etc. is a later step. The point now is
that the *gate* has teeth from the beginning.
"""
from __future__ import annotations

from typing import Any

from .base import Registry, obj, string


def _coerce(value: str) -> Any:
    low = value.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        return int(value)
    except ValueError:
        try:
            return float(value)
        except ValueError:
            return value


def register(registry: Registry, ctx) -> None:
    # --- drafting (safe) ----------------------------------------------------
    def draft_message(args: dict[str, Any]) -> str:
        to = (args.get("to") or "someone").strip()
        body = (args.get("body") or "").strip()
        return f"Draft to {to}:\n\n{body}\n\n(Not sent — say the word to send it.)"

    registry.add(
        "draft_message",
        "Write a draft message (email/text) for the user to review. This does "
        "NOT send anything. Use to compose; sending is a separate step.",
        obj(
            {"to": string("Recipient."), "body": string("Message body.")},
            required=["body"],
        ),
        draft_message,
    )

    # --- sending (gated) ----------------------------------------------------
    def send_message(args: dict[str, Any]) -> str:
        to = (args.get("to") or "").strip()
        body = (args.get("body") or "").strip()
        if not to or not body:
            return "I need both a recipient and a body to send."
        # Wire a real provider here later. For now we record the send.
        return f"Sent to {to}: {body[:80]}"

    registry.add(
        "send_message",
        "Send a message (email/text/DM) on the user's behalf. CONSEQUENTIAL: "
        "this reaches someone and can't be undone.",
        obj(
            {"to": string("Recipient."), "body": string("Message body.")},
            required=["to", "body"],
        ),
        send_message,
        consequential=True,
    )

    # --- spending (gated) ---------------------------------------------------
    def spend_money(args: dict[str, Any]) -> str:
        amount = args.get("amount")
        what = (args.get("description") or "").strip()
        return f"Charged {amount} for: {what}"

    registry.add(
        "spend_money",
        "Make a purchase or payment on the user's behalf. CONSEQUENTIAL: spends "
        "real money.",
        obj(
            {
                "amount": {"type": "number", "description": "Amount to spend."},
                "description": string("What it's for."),
            },
            required=["amount", "description"],
        ),
        spend_money,
        consequential=True,
    )

    # --- deleting (gated) ---------------------------------------------------
    def delete_data(args: dict[str, Any]) -> str:
        kind = (args.get("kind") or "").strip().lower()
        did = args.get("id")
        if did is None:
            return "I need the id of the thing to delete."
        if kind == "reminder":
            ok = ctx.reminders.delete(int(did))
        elif kind == "memory":
            ok = ctx.memory.remove(int(did))
        else:
            return "I can delete 'reminder' or 'memory' items by id."
        return f"Deleted {kind} #{did}." if ok else f"No {kind} #{did} found."

    registry.add(
        "delete_data",
        "Delete a stored item (a reminder or a memory fact) by id. "
        "CONSEQUENTIAL: removing data can't be undone.",
        obj(
            {
                "kind": {"type": "string", "enum": ["reminder", "memory"]},
                "id": {"type": "integer", "description": "Id of the item."},
            },
            required=["kind", "id"],
        ),
        delete_data,
        consequential=True,
    )

    # --- changing settings (gated) -----------------------------------------
    def change_settings(args: dict[str, Any]) -> str:
        key = (args.get("key") or "").strip()
        raw = args.get("value")
        if not key or raw is None:
            return "I need a config key and a value."
        value = _coerce(str(raw))
        ctx.config.set(key, value)
        return f"Set {key} = {value!r} in config.yaml."

    registry.add(
        "change_settings",
        "Change a configuration setting (dotted key in config.yaml, e.g. "
        "'brain.model' or 'heartbeat.enabled'). CONSEQUENTIAL: changes how Wren "
        "behaves.",
        obj(
            {
                "key": string("Dotted config key."),
                "value": string("New value (string/number/bool)."),
            },
            required=["key", "value"],
        ),
        change_settings,
        consequential=True,
    )
