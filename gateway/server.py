"""The Donald gateway HTTP/WebSocket server.

This is the single endpoint your Claude-designed UI talks to. It never exposes
Hermes or ElevenLabs directly — the UI speaks to Donald here, and the gateway
routes, gates, and streams.

Endpoints
---------
GET  /health            liveness + which pieces are configured/reachable
GET  /api/dashboard     current state snapshot (actions, status, metrics)
GET  /dashboard         HTML control panel with live polling
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
from .dashboard_state import get_dashboard_state
from .orchestrator import DonaldOrchestrator, Session

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

    @app.get("/api/dashboard")
    async def dashboard_api() -> dict:
        """Return current dashboard state: actions, status, metrics."""
        state = get_dashboard_state()
        return state.snapshot()

    @app.get("/dashboard")
    async def dashboard_page():
        """Serve the Hermes command center dashboard."""
        from fastapi.responses import HTMLResponse
        html = _dashboard_html()
        return HTMLResponse(content=html)

    @app.post("/api/dashboard/pause")
    async def dashboard_pause():
        """Pause the agent."""
        state = get_dashboard_state()
        state.pause()
        return {"status": "paused"}

    @app.post("/api/dashboard/resume")
    async def dashboard_resume():
        """Resume the agent."""
        state = get_dashboard_state()
        state.resume()
        return {"status": "resumed"}

    @app.post("/api/chat")
    async def chat(payload: dict) -> dict:
        session_id = str(payload.get("session_id") or "default")
        message = str(payload.get("message") or "").strip()
        if not message:
            return {"error": "message is required"}
        state = get_dashboard_state()
        state.set_user_message(message)
        reply = await orch.run(get_session(session_id), message)
        for event in reply.events:
            state.record_event(session_id, event)
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
                state = get_dashboard_state()
                state.set_user_message(message)
                async for event in orch.run_events(get_session(session_id), message):
                    state.record_event(session_id, event)
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


def _dashboard_html() -> str:
    """HTML for the Hermes Command Center control panel."""
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hermes Command Center</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            background: #0f172a;
            color: #e2e8f0;
            line-height: 1.5;
        }

        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }

        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 30px;
            border-bottom: 1px solid #334155;
            padding-bottom: 20px;
        }

        h1 {
            font-size: 28px;
            font-weight: 600;
        }

        .status-pill {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 8px 16px;
            background: #1e293b;
            border: 1px solid #475569;
            border-radius: 20px;
            font-size: 14px;
            font-weight: 500;
        }

        .status-live {
            background: #7c3aed;
            border-color: #6d28d9;
        }

        .status-paused {
            background: #dc2626;
            border-color: #b91c1c;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: currentColor;
            animation: pulse 2s infinite;
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }

        .controls {
            display: flex;
            gap: 10px;
        }

        button {
            padding: 8px 16px;
            border: 1px solid #475569;
            border-radius: 6px;
            background: #1e293b;
            color: #e2e8f0;
            cursor: pointer;
            font-weight: 500;
            transition: all 0.2s;
        }

        button:hover {
            background: #334155;
            border-color: #64748b;
        }

        button.primary {
            background: #3b82f6;
            border-color: #2563eb;
        }

        button.primary:hover {
            background: #2563eb;
        }

        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 16px;
            margin-bottom: 30px;
        }

        .stat-tile {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 16px;
        }

        .stat-label {
            font-size: 12px;
            font-weight: 600;
            text-transform: uppercase;
            color: #94a3b8;
            margin-bottom: 8px;
        }

        .stat-value {
            font-size: 24px;
            font-weight: 700;
            color: #3b82f6;
        }

        .section {
            margin-bottom: 30px;
        }

        h2 {
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 12px;
            text-transform: uppercase;
            color: #94a3b8;
        }

        .activity-feed {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            max-height: 400px;
            overflow-y: auto;
        }

        .activity-item {
            padding: 12px 16px;
            border-bottom: 1px solid #334155;
            font-size: 13px;
        }

        .activity-item:last-child {
            border-bottom: none;
        }

        .activity-item.ok {
            border-left: 3px solid #10b981;
        }

        .activity-item.error {
            border-left: 3px solid #ef4444;
        }

        .activity-item.pending {
            border-left: 3px solid #f59e0b;
        }

        .activity-item.declined {
            border-left: 3px solid #8b5cf6;
        }

        .activity-status {
            font-weight: 600;
            margin-right: 8px;
        }

        .activity-status.ok::before { content: "✓ "; color: #10b981; }
        .activity-status.error::before { content: "✕ "; color: #ef4444; }
        .activity-status.pending::before { content: "⟳ "; color: #f59e0b; }
        .activity-status.declined::before { content: "⊘ "; color: #8b5cf6; }

        .activity-task {
            margin-top: 4px;
            color: #cbd5e1;
            word-break: break-word;
        }

        .empty-state {
            padding: 32px 16px;
            text-align: center;
            color: #64748b;
        }

        .preview {
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 4px;
            padding: 8px 12px;
            margin-top: 8px;
            font-size: 12px;
            font-family: "Monaco", "Courier New", monospace;
            color: #cbd5e1;
            word-break: break-word;
            max-height: 100px;
            overflow-y: auto;
        }

        .last-message {
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 8px;
            padding: 16px;
            font-size: 13px;
            line-height: 1.6;
        }

        .timestamp {
            font-size: 11px;
            color: #64748b;
            margin-right: 8px;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🎛️ Hermes Command Center</h1>
            <div>
                <div class="status-pill" id="status">
                    <span class="status-dot"></span>
                    <span id="status-text">Loading...</span>
                </div>
            </div>
        </header>

        <div class="controls" style="margin-bottom: 20px;">
            <button id="btn-pause" class="primary">Stop</button>
            <button id="btn-resume">Resume</button>
        </div>

        <div class="stats">
            <div class="stat-tile">
                <div class="stat-label">Turns</div>
                <div class="stat-value" id="stat-turns">0</div>
            </div>
            <div class="stat-tile">
                <div class="stat-label">Hermes Actions</div>
                <div class="stat-value" id="stat-actions">0</div>
            </div>
            <div class="stat-tile">
                <div class="stat-label">Status</div>
                <div class="stat-value" id="stat-status">Ready</div>
            </div>
        </div>

        <div class="section">
            <h2>Live Activity</h2>
            <div class="activity-feed" id="activity-feed">
                <div class="empty-state">Waiting for activity...</div>
            </div>
        </div>

        <div class="section">
            <h2>Last User Input</h2>
            <div class="last-message" id="last-message">
                <p style="color: #64748b;">No messages yet</p>
            </div>
        </div>

        <div class="section">
            <h2>Last Response</h2>
            <div class="last-message" id="last-response">
                <p style="color: #64748b;">Waiting for response...</p>
            </div>
        </div>
    </div>

    <script>
        let paused = false;

        async function updateDashboard() {
            try {
                const resp = await fetch('/api/dashboard');
                const data = await resp.json();

                // Update status
                const statusPill = document.getElementById('status');
                const statusText = document.getElementById('status-text');
                paused = data.paused;

                if (paused) {
                    statusPill.className = 'status-pill status-paused';
                    statusText.textContent = '● HALTED';
                } else {
                    statusPill.className = 'status-pill status-live';
                    statusText.textContent = '● LIVE';
                }

                // Update stats
                document.getElementById('stat-turns').textContent = data.turn_count;
                document.getElementById('stat-actions').textContent = data.hermes_actions;
                document.getElementById('stat-status').textContent = paused ? 'Halted' : 'Ready';

                // Update activity feed
                const feed = document.getElementById('activity-feed');
                const actions = data.actions || [];

                if (actions.length === 0) {
                    feed.innerHTML = '<div class="empty-state">Waiting for activity...</div>';
                } else {
                    feed.innerHTML = actions.map(action => {
                        const ts = new Date(action.timestamp * 1000).toLocaleTimeString();
                        let html = `<div class="activity-item ${action.status}">
                            <span class="timestamp">${ts}</span>
                            <span class="activity-status ${action.status}"></span>
                            <strong>${action.name}</strong>`;

                        if (action.task) {
                            html += `<div class="activity-task">${escapeHtml(action.task.substring(0, 100))}${action.task.length > 100 ? '...' : ''}</div>`;
                        }

                        if (action.preview) {
                            html += `<div class="preview">${escapeHtml(action.preview.substring(0, 200))}${action.preview.length > 200 ? '...' : ''}</div>`;
                        }

                        if (action.error) {
                            html += `<div class="preview" style="color: #ef4444;">${escapeHtml(action.error.substring(0, 200))}</div>`;
                        }

                        html += '</div>';
                        return html;
                    }).join('');
                }

                // Update last message
                const lastMsg = document.getElementById('last-message');
                if (data.last_user_message) {
                    lastMsg.textContent = data.last_user_message;
                } else {
                    lastMsg.innerHTML = '<p style="color: #64748b;">No messages yet</p>';
                }

                // Update last response
                const lastResp = document.getElementById('last-response');
                if (data.last_response) {
                    lastResp.textContent = data.last_response;
                } else {
                    lastResp.innerHTML = '<p style="color: #64748b;">Waiting for response...</p>';
                }

            } catch (e) {
                console.error('Dashboard update failed:', e);
            }
        }

        function escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }

        document.getElementById('btn-pause').addEventListener('click', async () => {
            await fetch('/api/dashboard/pause', {method: 'POST'});
            updateDashboard();
        });

        document.getElementById('btn-resume').addEventListener('click', async () => {
            await fetch('/api/dashboard/resume', {method: 'POST'});
            updateDashboard();
        });

        // Initial load and then poll every 2 seconds
        updateDashboard();
        setInterval(updateDashboard, 2000);
    </script>
</body>
</html>"""


def main() -> None:  # pragma: no cover - thin runtime entrypoint
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    settings = load_settings()
    log.info("Donald gateway starting: %s", settings.redacted())
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port)


if __name__ == "__main__":  # pragma: no cover
    main()
