"""FastAPI app wiring the pipeline together.

Transport:
  * WebSocket ``/ws`` carries control + ``speak_segment`` / ``transcript_delta``
    events. The client sends ``{"type": "user_message", "text": ...}``.
  * ``GET /api/tts/{segment_id}`` streams the audio bytes for one segment.

The TTS endpoint already existed conceptually in any voice agent; the fix just
adds per-segment keys to a TTL'd in-memory store as each sentence is produced.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config, llm, tts
from .segment_stream import iter_sentences, stream_with_segments

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
log = logging.getLogger("voice-agent")

app = FastAPI(title="Voice Agent Latency Reference")

# TTL'd in-memory store of segment text, keyed by segment id.
# value = (text, expires_at_monotonic)
_segment_texts: dict[str, tuple[str, float]] = {}


def record_segment(segment_id: str, text: str) -> None:
    now = time.monotonic()
    # Lazy prune of expired entries.
    for k in [k for k, (_t, exp) in _segment_texts.items() if exp < now]:
        _segment_texts.pop(k, None)
    _segment_texts[segment_id] = (text, now + config.SEGMENT_TTL_S)


def get_segment_text(segment_id: str) -> str | None:
    entry = _segment_texts.get(segment_id)
    if entry is None:
        return None
    text, exp = entry
    if exp < time.monotonic():
        _segment_texts.pop(segment_id, None)
        return None
    return text


@app.get("/api/config")
async def get_config() -> dict:
    """Expose advisory settings (e.g. the VAD window) to the client."""
    return {
        "vad_silence_ms": config.VAD_SILENCE_MS,
        "tts_provider": config.TTS_PROVIDER,
        "llm_model": config.LLM_MODEL,
        "mock_llm": config.USE_MOCK_LLM,
    }


@app.get("/api/tts/{segment_id}")
async def tts_endpoint(segment_id: str):
    text = get_segment_text(segment_id)
    if text is None:
        return StreamingResponse(iter(()), status_code=404, media_type="text/plain")
    return StreamingResponse(tts.synthesize(text), media_type=tts.media_type())


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("type") != "user_message":
                continue

            user_text = msg.get("text", "")
            t0 = time.monotonic()
            log.info("user_message: %r", user_text)

            messages = [{"role": "user", "content": user_text}]
            sentences = iter_sentences(llm.stream_text(messages))

            await stream_with_segments(
                sentences=sentences,
                send_json=ws.send_json,
                record_segment=record_segment,
                voice=msg.get("voice", True),
                auto_continue=False,
                clock=lambda: time.monotonic(),
                log=log.info,
            )
            log.info("turn complete in %.2fs", time.monotonic() - t0)
    except WebSocketDisconnect:
        log.info("client disconnected")


# Serve the static client last so the API routes above take precedence.
_client_dir = Path(__file__).resolve().parent.parent / "client"
if _client_dir.is_dir():
    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(_client_dir / "index.html")

    app.mount("/static", StaticFiles(directory=_client_dir), name="static")
