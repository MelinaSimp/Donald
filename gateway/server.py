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

log = logging.getLogger("donald.gateway")


def build_orchestrator(settings: Settings) -> DonaldOrchestrator:
    """Wire the real connectors and the Anthropic brain from settings."""
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


def create_app(
    settings: Optional[Settings] = None,
    orchestrator: Optional[DonaldOrchestrator] = None,
):
    """Build the FastAPI app. ``orchestrator`` is injectable for tests."""
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.middleware.cors import CORSMiddleware
        from fastapi.responses import Response
    except ImportError as exc:  # pragma: no cover - dependency guard
        raise RuntimeError(
            "fastapi is required to run the gateway (pip install fastapi uvicorn)"
        ) from exc

    settings = settings or load_settings()
    orch = orchestrator or build_orchestrator(settings)
    sessions: Dict[str, Session] = {}

    def get_session(session_id: str) -> Session:
        sess = sessions.get(session_id)
        if sess is None:
            sess = Session(session_id=session_id)
            sessions[session_id] = sess
        return sess

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
        return {
            "status": "ok",
            "donald_model": settings.donald_model,
            "anthropic_configured": bool(settings.anthropic_api_key),
            "hermes_mode": settings.hermes_mode,
            "hermes_target": hermes_target,
            "hermes_reachable": hermes_ok,
            "voice_configured": settings.voice_configured,
        }

    @app.post("/api/chat")
    async def chat(payload: dict) -> dict:
        session_id = str(payload.get("session_id") or "default")
        message = str(payload.get("message") or "").strip()
        if not message:
            return {"error": "message is required"}
        reply = await orch.run(get_session(session_id), message)
        return {"text": reply.text, "events": reply.events}

    @app.post("/api/voice")
    async def voice(payload: dict):
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
                async for event in orch.run_events(get_session(session_id), message):
                    await websocket.send_json(event)
        except WebSocketDisconnect:
            return
        except Exception as exc:  # keep the socket from dying silently
            log.exception("ws turn failed")
            try:
                await websocket.send_json({"type": "error", "text": str(exc)})
            except Exception:
                pass

    return app


def main() -> None:  # pragma: no cover - thin runtime entrypoint
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    log.info("Donald gateway starting: %s", settings.redacted())
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
