"""The product API — accounts, auth, per-user integration tokens, run history.

One FastAPI app the desktop app / UI talks to. Every data route depends on
``current_user``, which resolves the bearer token to a user; there is no route
that returns data without that scoping, so tenants stay isolated.

    from backend.api import create_app
    app = create_app()            # uses DATABASE_URL / BACKEND_SECRET_KEY
    # uvicorn backend.api:app --reload   (module-level `app` is built lazily)
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field

from security.auth_ratelimit import AuthRateLimiter, client_ip
from security.bearer_auth import extract_bearer

from .billing import BillingError, BillingService
from .crypto import TokenCipher
from .db import DB, open_db
from .memory import MemoryStore
from .models import User
from .oauth import PROVIDERS, OAuthBroker, OAuthError
from .provider_api import ProviderAPI, ProviderError
from .updates import load_manifest, resolve_update
from .repo import (
    EmailTaken, RunRepo, SessionRepo, SubscriptionRepo, TokenRepo, UserRepo,
)


# ── request bodies ──────────────────────────────────────────────────────────
class SignupBody(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    display_name: str = Field(default="", max_length=120)
    country: str | None = Field(default=None, max_length=2)
    dob: str | None = None  # ISO date; presence-checked, not verified here
    accept_tos: bool = False


class LoginBody(BaseModel):
    email: EmailStr
    password: str


class TokenBody(BaseModel):
    secret: dict[str, Any] = Field(description="Provider token payload to encrypt")


class FactBody(BaseModel):
    content: str = Field(min_length=1, max_length=500)


class IssueBody(BaseModel):
    repo: str = Field(description="owner/name")
    title: str = Field(min_length=1, max_length=256)
    body: str = Field(default="", max_length=8000)
    confirm: bool = False


def create_app(
    db: DB | None = None,
    cipher: TokenCipher | None = None,
    rate_limiter: AuthRateLimiter | None = None,
    broker: OAuthBroker | None = None,
    billing: BillingService | None = None,
) -> FastAPI:
    db = db or open_db()
    cipher = cipher or TokenCipher()
    limiter = rate_limiter or AuthRateLimiter()
    users = UserRepo(db)
    sessions = SessionRepo(db)
    tokens = TokenRepo(db, cipher)
    runs = RunRepo(db)
    broker = broker or OAuthBroker(tokens)
    billing = billing or BillingService(SubscriptionRepo(db))
    provider_api = ProviderAPI(broker)
    memory = MemoryStore(db)

    app = FastAPI(title="Donald Backend", version="0.1.0")

    def guard_auth_rate(request: Request) -> str:
        """Per-IP brute-force guard for the auth endpoints. Returns the ip."""
        ip = client_ip(dict(request.headers), request.client.host if request.client else "?")
        allowed, retry_after = limiter.check(ip)
        if not allowed:
            raise HTTPException(
                status_code=429, detail="too many attempts",
                headers={"Retry-After": str(int(retry_after))},
            )
        return ip

    def current_user(authorization: str | None = Header(default=None)) -> User:
        token = extract_bearer(authorization)
        user_id = sessions.resolve(token) if token else None
        if not user_id:
            raise HTTPException(status_code=401, detail="invalid or missing token")
        user = users.by_id(user_id)
        if not user or user.status != "active":
            raise HTTPException(status_code=401, detail="account not available")
        return user

    # ── health ──────────────────────────────────────────────────────────────
    @app.get("/health")
    def health() -> dict:
        return {"ok": True, "engine": "postgres" if db.is_postgres else "sqlite"}

    # ── desktop auto-update (M6): what the Tauri updater polls ────────────────
    from fastapi import Response

    @app.get("/api/update/{target}/{arch}/{current_version}")
    def update_check(target: str, arch: str, current_version: str):
        upd = resolve_update(load_manifest(), target, arch, current_version)
        if not upd:
            return Response(status_code=204)  # up to date / no build for platform
        return upd

    # ── auth ──────────────────────────────────────────────────────────────────
    @app.post("/auth/signup")
    def signup(body: SignupBody, request: Request) -> dict:
        guard_auth_rate(request)
        if not body.accept_tos:
            raise HTTPException(status_code=400, detail="must accept terms of service")
        try:
            user = users.create(
                email=body.email, password=body.password,
                display_name=body.display_name, country=body.country,
                dob=body.dob, tos_accepted=body.accept_tos,
            )
        except EmailTaken:
            raise HTTPException(status_code=409, detail="email already registered")
        token = sessions.issue(user.id)
        return {"token": token, "user": user.public()}

    @app.post("/auth/login")
    def login(body: LoginBody, request: Request) -> dict:
        ip = guard_auth_rate(request)
        user = users.check_password(body.email, body.password)
        if not user:
            limiter.record_fail(ip)  # only failures count toward lockout
            raise HTTPException(status_code=401, detail="invalid credentials")
        token = sessions.issue(user.id)
        return {"token": token, "user": user.public()}

    @app.get("/auth/me")
    def me(user: User = Depends(current_user)) -> dict:
        return user.public()

    @app.post("/auth/logout")
    def logout(
        user: User = Depends(current_user),
        authorization: str | None = Header(default=None),
    ) -> dict:
        sessions.revoke(extract_bearer(authorization) or "")
        return {"ok": True}

    # ── integration tokens (per user, encrypted) ─────────────────────────────
    @app.get("/integrations")
    def list_integrations(user: User = Depends(current_user)) -> dict:
        return {"providers": tokens.providers(user.id)}

    @app.put("/integrations/{provider}")
    def put_integration(
        provider: str, body: TokenBody, user: User = Depends(current_user)
    ) -> dict:
        tokens.put(user.id, provider, body.secret)
        return {"ok": True, "provider": provider}

    @app.delete("/integrations/{provider}")
    def delete_integration(
        provider: str, user: User = Depends(current_user)
    ) -> dict:
        if not tokens.delete(user.id, provider):
            raise HTTPException(status_code=404, detail="not connected")
        return {"ok": True}

    # ── OAuth broker (M4): connect providers per user ────────────────────────
    @app.get("/oauth/providers")
    def oauth_providers(user: User = Depends(current_user)) -> dict:
        connected = set(tokens.providers(user.id))
        return {"providers": [
            {"name": name, "configured": broker.is_configured(name),
             "connected": name in connected}
            for name in PROVIDERS
        ]}

    @app.get("/integrations/{provider}/whoami")
    def integration_whoami(provider: str, user: User = Depends(current_user)) -> dict:
        """Prove a connected integration is usable: call the provider with the
        user's stored (auto-refreshed) token and return the account identity."""
        try:
            who = provider_api.whoami(user.id, provider)
        except ProviderError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        if who is None:
            raise HTTPException(status_code=404, detail="not connected")
        return who

    @app.post("/integrations/github/issue")
    def github_issue(body: IssueBody, user: User = Depends(current_user)) -> dict:
        """Consequential action behind a confirmation gate: without confirm:true
        it returns a preview; with it, it actually opens the issue."""
        try:
            return provider_api.create_github_issue(
                user.id, body.repo, body.title, body.body, confirm=body.confirm
            )
        except ProviderError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/oauth/{provider}/authorize")
    def oauth_authorize(provider: str, user: User = Depends(current_user)) -> dict:
        try:
            return {"authorize_url": broker.authorize_url(user.id, provider)}
        except OAuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.get("/oauth/{provider}/callback")
    def oauth_callback(provider: str, code: str = "", state: str = ""):
        # No bearer here — the signed state proves the user. On success, bounce
        # back to the app.
        try:
            broker.handle_callback(provider, code, state)
        except OAuthError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return RedirectResponse(url="/app/?connected=" + provider, status_code=303)

    # ── billing (M5): Stripe subscriptions + webhooks ────────────────────────
    @app.get("/billing/subscription")
    def billing_subscription(user: User = Depends(current_user)) -> dict:
        return {"configured": billing.is_configured(), **billing.subscription(user.id)}

    @app.post("/billing/checkout")
    def billing_checkout(user: User = Depends(current_user)) -> dict:
        try:
            return {"url": billing.start_checkout(user.id, user.email)}
        except BillingError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/billing/portal")
    def billing_portal(user: User = Depends(current_user)) -> dict:
        try:
            return {"url": billing.portal(user.id, user.email)}
        except BillingError as exc:
            raise HTTPException(status_code=400, detail=str(exc))

    @app.post("/billing/webhook")
    async def billing_webhook(request: Request) -> dict:
        payload = await request.body()
        sig = request.headers.get("stripe-signature", "")
        try:
            event_type = billing.handle_webhook(payload, sig)
        except BillingError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"received": True, "type": event_type}

    # ── memory (M2): what Donald remembers, visible + editable ───────────────
    @app.get("/memory")
    def memory_list(user: User = Depends(current_user)) -> dict:
        return {"facts": memory.facts_full(user.id)}

    @app.post("/memory")
    def memory_add(body: FactBody, user: User = Depends(current_user)) -> dict:
        fact_id = memory.add_fact(user.id, body.content)
        if not fact_id:
            raise HTTPException(status_code=400, detail="empty fact")
        return {"id": fact_id, "content": body.content.strip()}

    @app.delete("/memory/{item_id}")
    def memory_delete(item_id: str, user: User = Depends(current_user)) -> dict:
        if not memory.delete(user.id, item_id):
            raise HTTPException(status_code=404, detail="not found")
        return {"ok": True}

    # ── run history ───────────────────────────────────────────────────────────
    @app.get("/runs")
    def list_runs(user: User = Depends(current_user)) -> dict:
        return {"runs": [r.__dict__ for r in runs.list_for(user.id)]}

    return app
