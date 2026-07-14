"""M5 billing: checkout/portal via a fake Stripe client, webhook signature
verification, and subscription state driven by webhook events (not the redirect).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.billing import BillingError, BillingService, StripeClient, verify_stripe_signature
from backend.db import open_db
from backend.repo import SessionRepo, SubscriptionRepo, UserRepo

WEBHOOK_SECRET = "whsec_test"


class FakeStripe(StripeClient):
    def __init__(self):
        self.calls = []

    def create_customer(self, email):
        self.calls.append(("customer", email))
        return {"id": "cus_123", "email": email}

    def create_checkout_session(self, **form):
        self.calls.append(("checkout", form))
        return {"id": "cs_1", "url": "https://checkout.stripe.com/pay/cs_1"}

    def create_portal_session(self, **form):
        self.calls.append(("portal", form))
        return {"url": "https://billing.stripe.com/p/session/test"}


def _service(db):
    return BillingService(
        SubscriptionRepo(db), client=FakeStripe(),
        price_id="price_pro", webhook_secret=WEBHOOK_SECRET,
        success_url="https://app/x", cancel_url="https://app/y",
    )


def _sign(payload: bytes, secret=WEBHOOK_SECRET, t=None):
    t = t or int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}"


def _user(db, email="pay@example.com"):
    return UserRepo(db).create(email, "longenough1").id


# ── signature verification ────────────────────────────────────────────────────
def test_signature_roundtrip_and_rejects_tampering():
    payload = json.dumps({"type": "ping"}).encode()
    hdr = _sign(payload)
    assert verify_stripe_signature(payload, hdr, WEBHOOK_SECRET)["type"] == "ping"
    with pytest.raises(BillingError):
        verify_stripe_signature(payload + b"x", hdr, WEBHOOK_SECRET)     # tampered body
    with pytest.raises(BillingError):
        verify_stripe_signature(payload, hdr, "whsec_wrong")            # wrong secret
    with pytest.raises(BillingError):
        verify_stripe_signature(payload, _sign(payload, t=1), WEBHOOK_SECRET)  # stale


# ── checkout / portal ─────────────────────────────────────────────────────────
def test_checkout_creates_customer_and_session():
    db = open_db("sqlite://:memory:")
    svc = _service(db)
    uid = _user(db)
    url = svc.start_checkout(uid, "pay@example.com")
    assert url.startswith("https://checkout.stripe.com/")
    # Customer was created and remembered.
    assert svc.subs.get(uid)["stripe_customer_id"] == "cus_123"
    # Second checkout reuses the customer (no new create_customer call).
    svc.start_checkout(uid, "pay@example.com")
    assert [c[0] for c in svc.client.calls].count("customer") == 1
    # client_reference_id ties the session to the user.
    checkout_form = next(c[1] for c in svc.client.calls if c[0] == "checkout")
    assert checkout_form["client_reference_id"] == uid


def test_unconfigured_billing_raises():
    db = open_db("sqlite://:memory:")
    svc = BillingService(SubscriptionRepo(db), client=None, price_id="")
    assert not svc.is_configured()
    with pytest.raises(BillingError):
        svc.start_checkout(_user(db), "x@x.com")


# ── webhooks drive plan state ─────────────────────────────────────────────────
def test_checkout_completed_webhook_upgrades_to_pro():
    db = open_db("sqlite://:memory:")
    svc = _service(db)
    uid = _user(db)
    svc.apply_event({
        "type": "checkout.session.completed",
        "data": {"object": {"client_reference_id": uid, "customer": "cus_123",
                            "subscription": "sub_1"}},
    })
    sub = svc.subscription(uid)
    assert sub["plan"] == "pro" and sub["status"] == "active"


def test_subscription_deleted_webhook_downgrades():
    db = open_db("sqlite://:memory:")
    svc = _service(db)
    uid = _user(db)
    svc.subs.upsert(uid, stripe_customer_id="cus_123", plan="pro", status="active")
    svc.apply_event({
        "type": "customer.subscription.deleted",
        "data": {"object": {"customer": "cus_123", "id": "sub_1", "status": "canceled"}},
    })
    sub = svc.subscription(uid)
    assert sub["plan"] == "free" and sub["status"] == "canceled"


# ── API wiring ────────────────────────────────────────────────────────────────
def test_api_checkout_and_webhook_flow():
    db = open_db("sqlite://:memory:")
    svc = _service(db)
    client = TestClient(create_app(db=db, billing=svc))
    uid = _user(db, "flow@example.com")
    token = SessionRepo(db).issue(uid)
    hdr = {"Authorization": f"Bearer {token}"}

    assert client.get("/billing/subscription", headers=hdr).json()["plan"] == "free"
    r = client.post("/billing/checkout", headers=hdr)
    assert r.status_code == 200 and "checkout.stripe.com" in r.json()["url"]

    # Simulate Stripe calling our webhook.
    payload = json.dumps({
        "type": "checkout.session.completed",
        "data": {"object": {"client_reference_id": uid, "customer": "cus_123",
                            "subscription": "sub_1"}},
    }).encode()
    wr = client.post("/billing/webhook", content=payload,
                     headers={"stripe-signature": _sign(payload)})
    assert wr.status_code == 200 and wr.json()["received"]
    assert client.get("/billing/subscription", headers=hdr).json()["plan"] == "pro"


def test_api_webhook_bad_signature_rejected():
    db = open_db("sqlite://:memory:")
    client = TestClient(create_app(db=db, billing=_service(db)))
    r = client.post("/billing/webhook", content=b"{}",
                    headers={"stripe-signature": "t=1,v1=deadbeef"})
    assert r.status_code == 400
