"""Stripe integration via MCP server (Tier 6+).

Manage payments, invoices, and subscription billing.
Requires Stripe API key and MCP server connection.
Phase 3 integration — stub ready for production.
Note: All payment actions are gated (consequential=True).
"""
from __future__ import annotations

from typing import Any

from .base import Registry, obj, string


def register(registry: Registry, ctx) -> None:
    def create_invoice(args: dict[str, Any]) -> str:
        """Create a new invoice for a customer."""
        customer_id = (args.get("customer_id") or "").strip()
        if not customer_id:
            return "I need a Stripe customer ID."

        description = (args.get("description") or "").strip()
        amount_cents = int(args.get("amount_cents", 0))
        if amount_cents <= 0:
            return "I need an amount (in cents)."

        # Stub: In production, call Stripe API
        amount_dollars = amount_cents / 100.0
        return f"TODO: Create ${amount_dollars} invoice for customer {customer_id} (requires Stripe API)"

    def list_charges(args: dict[str, Any]) -> str:
        """List recent charges/transactions."""
        limit = min(int(args.get("limit", 10)), 100)
        # Stub
        return f"TODO: List {limit} recent Stripe charges (requires Stripe API)"

    def refund_payment(args: dict[str, Any]) -> str:
        """Refund a payment."""
        charge_id = (args.get("charge_id") or "").strip()
        if not charge_id:
            return "I need a Stripe charge ID."

        amount_cents = int(args.get("amount_cents", 0))
        # Stub
        return f"TODO: Refund charge {charge_id} (requires Stripe API)"

    def get_balance(args: dict[str, Any]) -> str:
        """Get the current Stripe account balance."""
        # Stub
        return "TODO: Get Stripe account balance (requires Stripe API)"

    registry.add(
        "create_invoice",
        "Create a new Stripe invoice for a customer. "
        "Requires a customer ID and amount in cents (e.g., 9999 = $99.99).",
        obj(
            {
                "customer_id": string("Stripe customer ID."),
                "description": string("Invoice description or memo."),
                "amount_cents": {"type": "integer", "description": "Amount in cents (e.g., 9999 = $99.99)."},
            },
            required=["customer_id", "amount_cents"],
        ),
        create_invoice,
        consequential=True,
    )
    registry.add(
        "list_charges",
        "List recent Stripe charges and transactions.",
        obj({"limit": {"type": "integer", "description": "Max results (1-100, default 10)."}}),
        list_charges,
    )
    registry.add(
        "refund_payment",
        "Refund a Stripe charge (partially or fully).",
        obj(
            {
                "charge_id": string("Stripe charge ID."),
                "amount_cents": {"type": "integer", "description": "Amount in cents. Omit for full refund."},
            },
            required=["charge_id"],
        ),
        refund_payment,
        consequential=True,
    )
    registry.add(
        "get_balance",
        "Check your Stripe account balance and payouts.",
        obj({}),
        get_balance,
    )
