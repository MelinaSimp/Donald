from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import logging
import os
from pathlib import Path

from server.config import settings
from server.db import init_db, create_session, get_cached_tts_text, prune_expired_tts_cache
from server.auth import require_auth, validate_token

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Donald", debug=settings.debug)

# Initialize database on startup
@app.on_event("startup")
async def startup():
    init_db()
    logger.info("Database initialized")


# Health check
@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


# Shell HTML (no-cache)
@app.get("/", response_class=FileResponse)
async def shell():
    shell_path = Path(__file__).parent.parent / "frontend" / "index.html"
    if not shell_path.exists():
        raise HTTPException(status_code=404, detail="Shell not found")
    return FileResponse(
        shell_path,
        headers={"Cache-Control": "no-store, must-revalidate"},
        media_type="text/html",
    )


# TTS endpoint (token-gated, non-evicting on read)
@app.get("/api/tts/{turn_id}")
async def get_tts(turn_id: str, request: Request):
    require_auth(request)

    # Check cache
    text = get_cached_tts_text(turn_id)
    if not text:
        raise HTTPException(status_code=404, detail="TTS not found or expired")

    # TODO: Call ElevenLabs API to stream MP3
    # For now, return a placeholder
    return StreamingResponse(
        iter([b"placeholder mp3 bytes"]),
        media_type="audio/mpeg",
        headers={
            "Content-Type": "audio/mpeg",
            "Cache-Control": "private, max-age=3600",
        },
    )


# WebSocket voice loop (token-gated)
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # Validate token from query param or header before accepting
    if not validate_token(websocket):
        await websocket.close(code=1008, reason="Unauthorized")
        return

    await websocket.accept()
    logger.info("WebSocket client connected")

    session_id = create_session()
    logger.info(f"Created session {session_id}")

    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            logger.info(f"WS message: {message_type}")

            if message_type == "start_listening":
                # Client wants to start mic capture
                await websocket.send_json({"type": "start_mic"})

            elif message_type == "stop_listening":
                # Client has stopped capturing (VAD or user tap)
                # TODO: Finalize Deepgram transcript, send back transcript
                pass

            elif message_type == "audio_frame":
                # Raw audio frame from client (base64-encoded PCM)
                # TODO: Forward to Deepgram streaming
                pass

            else:
                logger.warning(f"Unknown message type: {message_type}")

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        await websocket.close(code=1011, reason="Internal error")


# Serve PWA static assets (scene.js, sw.js, manifest.webmanifest)
frontend_path = Path(__file__).parent.parent / "frontend"
if frontend_path.exists():
    app.mount("/static", StaticFiles(directory=frontend_path), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app, host=settings.host, port=settings.port, log_level="info"
    )
