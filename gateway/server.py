"""The Donald gateway HTTP/WebSocket server.

This is the single endpoint your Claude-designed UI talks to. It never exposes
Hermes or ElevenLabs directly — the UI speaks to Donald here, and the gateway
routes, gates, and streams.

Endpoints
---------
GET  /health            liveness + which pieces are configured/reachable
POST /api/chat          one-shot turn -> {text, events}
POST /api/voice         ad-hoc text-to-speech -> audio/mpeg
WS   /ws                streaming chat: send {type:"chat", session_id, message},
                        receive a stream of orchestrator events (delta,
                        tool_call, tool_result, voice, final)

Auth is optional: pass an ``auth`` object (see backend.gateway_auth.GatewayAuth)
to require a bearer token on /api/chat and /ws and record each turn as a
per-user agent run. With no ``auth`` the server is single-user and open, exactly
as before (that's the mode the gateway's own tests use).

Run it::

    pip install -r requirements.txt
    # set ANTHROPIC_API_KEY, HERMES_API_KEY, ELEVENLABS_* (see .env.example)
    python -m gateway.server
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from .config import Settings, load_settings
from .connectors.hermes import HermesConnector
from .connectors.voice import ElevenLabsVoice
from .orchestrator import DonaldOrchestrator, Session

# FastAPI is a hard dependency of the server, but keep import failure friendly:
# these names must live in module globals so FastAPI can resolve the route
# annotations (which `from __future__ import annotations` turns into strings).
try:
    from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import Response

    _FASTAPI_OK = True
except ImportError:  # pragma: no cover - dependency guard
    _FASTAPI_OK = False


def _require_fastapi() -> None:
    if not _FASTAPI_OK:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "fastapi is required to run the gateway (pip install fastapi uvicorn)"
        )


log = logging.getLogger("donald.gateway")


def build_orchestrator(settings: Settings) -> DonaldOrchestrator:
    """Wire the real connectors and the Anthropic brain from settings."""
    if settings.donald_provider == "openai":
        from .connectors.openai_brain import OpenAICompatBrain

        llm = OpenAICompatBrain(
            base_url=settings.donald_base_url,
            api_key=settings.donald_api_key,
        )
    else:
        try:
            from anthropic import AsyncAnthropic
        except ImportError as exc:  # pragma: no cover - dependency guard
            raise RuntimeError(
                "anthropic is required to run the gateway (pip install anthropic)"
            ) from exc

        llm = AsyncAnthropic(api_key=settings.anthropic_api_key)
    if settings.hermes_mode == "cli":
        from .connectors.hermes_cli import HermesCliConnector

        hermes = HermesCliConnector(
            container=settings.hermes_docker_container,
            cli_path=settings.hermes_cli_path,
            extra_args=settings.hermes_cli_extra_args,
            model=settings.hermes_model if settings.hermes_model != "hermes" else None,
            timeout_s=settings.hermes_timeout_s,
        )
    else:
        hermes = HermesConnector(
            base_url=settings.hermes_base_url,
            api_key=settings.hermes_api_key,
            model=settings.hermes_model,
            timeout_s=settings.hermes_timeout_s,
        )
    voice = ElevenLabsVoice(
        api_key=settings.elevenlabs_api_key,
        voice_id=settings.elevenlabs_voice_id,
        model=settings.elevenlabs_model,
    ) if settings.voice_enabled else None

    return DonaldOrchestrator(
        llm=llm, hermes=hermes, settings=settings, voice=voice
    )


def add_gateway_routes(app, orch: DonaldOrchestrator, settings: Settings, auth=None):
    """Attach the chat/voice/ws routes to ``app``.

    Factored out so the standalone gateway (``create_app``) and the combined
    product server (``serve.py``, which mounts these onto the backend app) share
    one implementation. ``auth``, when present, gates /api/chat and /ws behind a
    bearer token and records each turn as a per-user agent run.
    """
    _require_fastapi()
    sessions: Dict[str, Session] = {}

    def get_session(session_id: str) -> Session:
        sess = sessions.get(session_id)
        if sess is None:
            sess = Session(session_id=session_id)
            sessions[session_id] = sess
        return sess

    def require_user(authorization: Optional[str] = None, token: Optional[str] = None):
        """Return the user_id for the request, or None when auth is disabled."""
        if auth is None:
            return None
        user_id = auth.user_for(authorization=authorization, token=token)
        if not user_id:
            raise HTTPException(status_code=401, detail="invalid or missing token")
        return user_id

    @app.post("/api/chat")
    async def chat(payload: dict, request: Request) -> dict:
        user_id = require_user(authorization=request.headers.get("authorization"))
        session_id = str(payload.get("session_id") or "default")
        message = str(payload.get("message") or "").strip()
        if not message:
            return {"error": "message is required"}
        # Namespacing by user keeps two tenants from sharing a conversation.
        key = f"{user_id}:{session_id}" if user_id else session_id
        run_id = auth.start_run(user_id) if (auth and user_id) else None
        reply = await orch.run(get_session(key), message)
        if run_id:
            auth.finish_run(user_id, run_id, reply.text[:280])
        return {"text": reply.text, "events": reply.events}

    @app.post("/api/voice")
    async def voice(payload: dict, request: Request):
        require_user(authorization=request.headers.get("authorization"))
        text = str(payload.get("text") or "").strip()
        if orch.voice is None or not orch.voice.configured:
            return Response(
                content=b'{"error":"voice not configured"}',
                media_type="application/json",
                status_code=503,
            )
        result = await orch.voice.synthesize(text)
        if not result.ok:
            return Response(
                content=f'{{"error":"{result.error}"}}'.encode(),
                media_type="application/json",
                status_code=502,
            )
        return Response(content=result.audio, media_type=result.mime)

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        await websocket.accept()
        user_id = None
        if auth is not None:
            # Browsers can't set Authorization on a WS upgrade, so also accept
            # ?token=... on the query string.
            user_id = auth.user_for(
                authorization=websocket.headers.get("authorization"),
                token=websocket.query_params.get("token"),
            )
            if not user_id:
                await websocket.send_json({"type": "error", "text": "unauthorized"})
                await websocket.close(code=4401)
                return
        try:
            while True:
                msg = await websocket.receive_json()
                if msg.get("type") != "chat":
                    await websocket.send_json(
                        {"type": "error", "text": "expected {type:'chat', ...}"}
                    )
                    continue
                session_id = str(msg.get("session_id") or "default")
                message = str(msg.get("message") or "").strip()
                if not message:
                    await websocket.send_json(
                        {"type": "error", "text": "message is required"}
                    )
                    continue
                key = f"{user_id}:{session_id}" if user_id else session_id
                run_id = auth.start_run(user_id) if (auth and user_id) else None
                final_text = ""
                async for event in orch.run_events(get_session(key), message):
                    if event.get("type") == "final":
                        final_text = str(event.get("text") or "")
                    await websocket.send_json(event)
                if run_id:
                    auth.finish_run(user_id, run_id, final_text[:280])
        except WebSocketDisconnect:
            return
        except Exception as exc:  # keep the socket from dying silently
            log.exception("ws turn failed")
            try:
                await websocket.send_json({"type": "error", "text": str(exc)})
            except Exception:
                pass

    return app


def create_app(
    settings: Optional[Settings] = None,
    orchestrator: Optional[DonaldOrchestrator] = None,
    auth=None,
):
    """Build the standalone gateway FastAPI app. ``orchestrator`` is injectable
    for tests; ``auth`` is optional (see ``add_gateway_routes``)."""
    _require_fastapi()
    settings = settings or load_settings()
    orch = orchestrator or build_orchestrator(settings)

    app = FastAPI(title="Donald Gateway", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health() -> dict:
        hermes_ok = await orch.hermes.health()
        hermes_target = (
            (settings.hermes_docker_container or "local CLI")
            if settings.hermes_mode == "cli"
            else settings.hermes_base_url
        )
        brain_configured = bool(
            settings.donald_api_key
            if settings.donald_provider == "openai"
            else settings.anthropic_api_key
        )
        return {
            "status": "ok",
            "donald_provider": settings.donald_provider,
            "donald_model": settings.donald_model,
            "brain_configured": brain_configured,
            "hermes_mode": settings.hermes_mode,
            "hermes_target": hermes_target,
            "hermes_reachable": hermes_ok,
            "voice_configured": settings.voice_configured,
        }

    add_gateway_routes(app, orch, settings, auth=auth)
    return app


def main() -> None:  # pragma: no cover - thin runtime entrypoint
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    log.info("Donald gateway starting: %s", settings.redacted())
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
