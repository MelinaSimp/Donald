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

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, EmailStr, Field

from security.bearer_auth import extract_bearer

from .crypto import TokenCipher
from .db import DB, open_db
from .models import User
from .repo import EmailTaken, RunRepo, SessionRepo, TokenRepo, UserRepo


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


def create_app(db: DB | None = None, cipher: TokenCipher | None = None) -> FastAPI:
    db = db or open_db()
    cipher = cipher or TokenCipher()
    users = UserRepo(db)
    sessions = SessionRepo(db)
    tokens = TokenRepo(db, cipher)
    runs = RunRepo(db)

    app = FastAPI(title="Donald Backend", version="0.1.0")

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

    # ── auth ──────────────────────────────────────────────────────────────────
    @app.post("/auth/signup")
    def signup(body: SignupBody) -> dict:
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
    def login(body: LoginBody) -> dict:
        user = users.check_password(body.email, body.password)
        if not user:
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

    # ── run history ───────────────────────────────────────────────────────────
    @app.get("/runs")
    def list_runs(user: User = Depends(current_user)) -> dict:
        return {"runs": [r.__dict__ for r in runs.list_for(user.id)]}

    return app
