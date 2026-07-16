"""The combined Donald server — one process, one port.

Mounts the backend product API (accounts, auth, encrypted integration tokens,
run history) and the gateway (authenticated, per-user chat/voice/WebSocket) onto
a single FastAPI app that shares one database. This is what the desktop app
talks to.

    pip install -r requirements.txt
    export BACKEND_SECRET_KEY=...        # see .env.example
    # (DATABASE_URL optional; defaults to SQLite for local dev)
    uvicorn "serve:create_app" --factory --host 0.0.0.0 --port 8000

Routes:
    /health, /auth/*, /integrations/*, /runs   (backend)
    /api/chat, /api/voice, /ws                 (gateway, bearer-gated)
"""

from __future__ import annotations

import pathlib

_WEBUI = pathlib.Path(__file__).parent / "webui"


def mount_webui(app):
    """Serve the static web shell at /app and redirect / -> /app/.

    Kept separate from create_app so it can be tested without building the
    orchestrator (which needs model/connector config).
    """
    from fastapi.responses import RedirectResponse
    from fastapi.staticfiles import StaticFiles

    @app.get("/")
    def _root():
        return RedirectResponse("/app/")

    app.mount("/app", StaticFiles(directory=str(_WEBUI), html=True), name="webui")
    return app


def create_app():
    from backend.agent_tools import IntegrationTools
    from backend.api import create_app as create_backend_app
    from backend.crypto import TokenCipher
    from backend.db import open_db
    from backend.gateway_auth import GatewayAuth
    from backend.memory_service import MemoryService
    from backend.oauth import OAuthBroker
    from backend.provider_api import ProviderAPI
    from backend.repo import TokenRepo
    from gateway.config import load_settings
    from gateway.server import add_gateway_routes, build_orchestrator

    db = open_db()  # DATABASE_URL or SQLite; runs migrations
    app = create_backend_app(db=db)  # /health, /auth, /integrations, /oauth, /billing…

    # One ProviderAPI over the same broker the backend uses; bind it per user so
    # Donald's tools act on the right person's connected accounts.
    provider_api = ProviderAPI(OAuthBroker(TokenRepo(db, TokenCipher())))
    tools_for = lambda user_id: IntegrationTools(provider_api, user_id)

    settings = load_settings()
    orch = build_orchestrator(settings)
    add_gateway_routes(
        app, orch, settings, auth=GatewayAuth(db), memory=MemoryService(db),
        integrations=tools_for,
    )
    mount_webui(app)
    return app


if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    uvicorn.run(create_app(), host="0.0.0.0", port=8000)
