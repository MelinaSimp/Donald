"""Billing (M5) — Stripe subscriptions + webhooks + plan gating.

Checkout and the customer portal are created via a thin, injectable Stripe
client (so tests never call Stripe). Subscription *state* is defined by webhooks,
not by the checkout redirect — the redirect only tells the browser "we're done";
the webhook is what actually flips the user to `pro`. We verify every webhook's
signature before trusting it.

    POST /billing/checkout   (bearer) -> { url }   open Stripe Checkout
    POST /billing/portal     (bearer) -> { url }   manage/cancel subscription
    POST /billing/webhook              -> 200       Stripe -> us (signed)
    GET  /billing/subscription (bearer) -> { plan, status, current_period_end }
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import time
from typing import Any, Optional

from .repo import SubscriptionRepo


class BillingError(Exception):
    pass


def verify_stripe_signature(payload: bytes, sig_header: str, secret: str, tolerance: int = 300) -> dict:
    """Verify a Stripe webhook signature (scheme: ``t=...,v1=...``) and return
    the parsed event. Raises BillingError on any mismatch or staleness."""
    parts = dict(
        p.split("=", 1) for p in sig_header.split(",") if "=" in p
    ) if sig_header else {}
    t, v1 = parts.get("t"), parts.get("v1")
    if not t or not v1:
        raise BillingError("malformed signature header")
    signed = f"{t}.".encode() + payload
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(v1, expected):
        raise BillingError("bad webhook signature")
    if abs(int(time.time()) - int(t)) > tolerance:
        raise BillingError("webhook timestamp outside tolerance")
    return json.loads(payload)


class StripeClient:
    """Minimal Stripe REST wrapper over the injectable HTTP client. Only the
    calls the service needs; swap in the official ``stripe`` SDK later if wanted."""

    def __init__(self, secret_key: str, http: Any | None = None) -> None:
        self.secret_key = secret_key
        self._http = http

    def _client(self):
        if self._http is None:
            import httpx

            self._http = httpx.Client(timeout=30.0)
        return self._http

    def _post(self, path: str, form: dict[str, str]) -> dict:
        resp = self._client().post(
            f"https://api.stripe.com/v1/{path}",
            data=form,
            headers={"Authorization": f"Bearer {self.secret_key}"},
        )
        if getattr(resp, "status_code", 200) >= 400:
            raise BillingError(f"stripe {path} returned {resp.status_code}")
        return resp.json()

    def create_customer(self, email: str) -> dict:
        return self._post("customers", {"email": email})

    def create_checkout_session(self, **form: str) -> dict:
        return self._post("checkout/sessions", form)

    def create_portal_session(self, **form: str) -> dict:
        return self._post("billing_portal/sessions", form)


class BillingService:
    def __init__(
        self,
        subs: SubscriptionRepo,
        client: Optional[StripeClient] = None,
        *,
        price_id: str | None = None,
        webhook_secret: str | None = None,
        success_url: str | None = None,
        cancel_url: str | None = None,
    ) -> None:
        self.subs = subs
        key = os.getenv("STRIPE_SECRET_KEY")
        self.client = client or (StripeClient(key) if key else None)
        self.price_id = price_id or os.getenv("STRIPE_PRICE_ID", "")
        self.webhook_secret = webhook_secret or os.getenv("STRIPE_WEBHOOK_SECRET", "")
        base = os.getenv("OAUTH_REDIRECT_BASE", "")
        self.success_url = success_url or os.getenv("BILLING_SUCCESS_URL", f"{base}/app/?billing=success")
        self.cancel_url = cancel_url or os.getenv("BILLING_CANCEL_URL", f"{base}/app/?billing=cancel")

    def is_configured(self) -> bool:
        return self.client is not None and bool(self.price_id)

    def _require(self) -> None:
        if not self.is_configured():
            raise BillingError("billing is not configured (set STRIPE_SECRET_KEY/STRIPE_PRICE_ID)")

    def _customer_id(self, user_id: str, email: str) -> str:
        sub = self.subs.get(user_id)
        if sub.get("stripe_customer_id"):
            return sub["stripe_customer_id"]
        customer = self.client.create_customer(email)
        self.subs.upsert(user_id, stripe_customer_id=customer["id"])
        return customer["id"]

    def start_checkout(self, user_id: str, email: str) -> str:
        self._require()
        customer_id = self._customer_id(user_id, email)
        session = self.client.create_checkout_session(**{
            "mode": "subscription",
            "customer": customer_id,
            "client_reference_id": user_id,   # ties the webhook back to the user
            "line_items[0][price]": self.price_id,
            "line_items[0][quantity]": "1",
            "success_url": self.success_url,
            "cancel_url": self.cancel_url,
        })
        return session["url"]

    def portal(self, user_id: str, email: str) -> str:
        self._require()
        customer_id = self._customer_id(user_id, email)
        session = self.client.create_portal_session(
            customer=customer_id, return_url=self.success_url
        )
        return session["url"]

    def subscription(self, user_id: str) -> dict:
        sub = self.subs.get(user_id)
        return {
            "plan": sub["plan"], "status": sub["status"],
            "current_period_end": sub.get("current_period_end"),
        }

    # ── webhooks: the source of truth for subscription state ───────────────
    def handle_webhook(self, payload: bytes, sig_header: str) -> str:
        if not self.webhook_secret:
            raise BillingError("STRIPE_WEBHOOK_SECRET is not set")
        event = verify_stripe_signature(payload, sig_header, self.webhook_secret)
        self.apply_event(event)
        return event.get("type", "")

    def apply_event(self, event: dict) -> None:
        etype = event.get("type", "")
        obj = event.get("data", {}).get("object", {})
        if etype == "checkout.session.completed":
            user_id = obj.get("client_reference_id")
            if user_id:
                self.subs.upsert(
                    user_id, plan="pro", status="active",
                    stripe_customer_id=obj.get("customer"),
                    stripe_subscription_id=obj.get("subscription"),
                )
        elif etype in ("customer.subscription.updated", "customer.subscription.deleted"):
            user_id = self.subs.by_customer(obj.get("customer", ""))
            if user_id:
                status = obj.get("status", "canceled")
                active = status in ("active", "trialing")
                self.subs.upsert(
                    user_id, status=status, plan="pro" if active else "free",
                    stripe_subscription_id=obj.get("id"),
                    current_period_end=_period_end(obj.get("current_period_end")),
                )


def _period_end(epoch: Any) -> str | None:
    if not epoch:
        return None
    from datetime import datetime, timezone

    return datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
