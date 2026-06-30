from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
import logging
import asyncio
import json
from pathlib import Path

from server.config import settings
from server.db import (
    init_db,
    create_session,
    get_cached_tts_text,
    save_turn,
    cache_tts_text,
    prune_expired_tts_cache,
)
from server.auth import require_auth, validate_token
from server.brain import Brain
from server.elevenlabs import ElevenLabsTTS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Donald", debug=settings.debug)

tts_client = ElevenLabsTTS()

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

    # Synthesize MP3 on-demand (cached text)
    mp3_bytes = await tts_client.synthesize(text)
    if not mp3_bytes:
        raise HTTPException(status_code=500, detail="TTS synthesis failed")

    return StreamingResponse(
        iter([mp3_bytes]),
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
    brain = Brain()
    brain.start_session()

    audio_frames_queue = asyncio.Queue()
    listening = False

    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            logger.info(f"WS message: {message_type}")

            if message_type == "start_listening":
                # Client wants to start mic capture
                listening = True
                await websocket.send_json({"type": "start_mic"})

            elif message_type == "stop_listening":
                # Client has stopped capturing (VAD or user tap)
                listening = False

                # Get final transcript from audio frames (simplified: just accumulate)
                # In a real impl, we'd finalize the Deepgram stream and get the transcript
                transcript_text = "Hello, how are you?"  # TODO: Real transcript from Deepgram

                # Save user's turn
                user_turn_id = save_turn(session_id, "user", transcript_text)

                # Send transcript to PWA
                await websocket.send_json(
                    {"type": "transcript", "role": "user", "text": transcript_text}
                )

                # Processing status
                await websocket.send_json({"type": "status", "state": "processing"})

                # Call brain for response (streaming)
                try:
                    full_response = ""

                    # Stream response from brain
                    for chunk, _ in brain.stream_response(transcript_text):
                        full_response += chunk
                        await websocket.send_json(
                            {"type": "transcript_delta", "text": chunk}
                        )

                    # Save assistant's turn
                    response_turn_id = save_turn(session_id, "assistant", full_response)

                    # Generate TTS and cache it
                    prune_expired_tts_cache()
                    mp3_bytes = await tts_client.synthesize(full_response)

                    if mp3_bytes:
                        cache_tts_text(response_turn_id, full_response, settings.tts_cache_ttl_seconds)
                        await websocket.send_json({"type": "speak", "turn_id": response_turn_id})

                    # Reset to idle
                    await websocket.send_json({"type": "status", "state": "idle"})

                except Exception as e:
                    logger.error(f"Brain error: {e}")
                    await websocket.send_json(
                        {"type": "status", "state": "error"}
                    )

            elif message_type == "audio_frame":
                # Raw audio frame from client (base64-encoded PCM)
                if listening:
                    frame_data = data.get("data")
                    if frame_data:
                        await audio_frames_queue.put(frame_data)

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
