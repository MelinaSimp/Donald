"""Text-to-speech providers.

Each provider is an async generator of audio bytes, so the server can stream
them straight to the client with ``StreamingResponse`` — the bytes start
flowing as soon as the TTS produces them, instead of buffering the whole clip
first.

  * ``mock_tts`` — generates a short silent WAV sized to the text length. No
    network, no key; lets the project run and be tested offline. (It's silent,
    but it plays and has a real duration, so the client audio queue, chaining,
    and interrupt logic all exercise correctly.)

  * ``openai_tts`` — streams MP3 bytes from OpenAI's TTS endpoint. A sketch of
    the real thing; confirm your provider actually streams on the wire.
"""

from __future__ import annotations

import struct
from typing import AsyncIterator

from . import config

_SAMPLE_RATE = 24000
_CHUNK = 4096


def _wav_header(num_samples: int) -> bytes:
    """Minimal 16-bit mono PCM WAV header."""
    data_bytes = num_samples * 2
    return b"RIFF" + struct.pack("<I", 36 + data_bytes) + b"WAVE" + (
        b"fmt " + struct.pack("<IHHIIHH", 16, 1, 1, _SAMPLE_RATE, _SAMPLE_RATE * 2, 2, 16)
    ) + b"data" + struct.pack("<I", data_bytes)


async def mock_tts(text: str) -> AsyncIterator[bytes]:
    """Yield a silent WAV whose duration scales with the text length."""
    # ~60ms of audio per character, clamped, so longer sentences take longer.
    seconds = max(0.4, min(6.0, len(text) * 0.06))
    num_samples = int(seconds * _SAMPLE_RATE)
    yield _wav_header(num_samples)
    silence = b"\x00\x00" * (_CHUNK // 2)
    remaining = num_samples
    while remaining > 0:
        n = min(remaining, _CHUNK // 2)
        yield silence[: n * 2]
        remaining -= n


async def openai_tts(text: str) -> AsyncIterator[bytes]:
    """Stream MP3 bytes from OpenAI TTS. Requires OPENAI_API_KEY + httpx."""
    import os

    import httpx

    url = "https://api.openai.com/v1/audio/speech"
    headers = {"Authorization": f"Bearer {os.environ['OPENAI_API_KEY']}"}
    payload = {
        "model": config.OPENAI_TTS_MODEL,
        "voice": config.OPENAI_TTS_VOICE,
        "input": text,
        "response_format": "mp3",
    }
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream("POST", url, headers=headers, json=payload) as resp:
            resp.raise_for_status()
            async for chunk in resp.aiter_bytes():
                if chunk:
                    yield chunk


def media_type() -> str:
    return "audio/mpeg" if config.TTS_PROVIDER == "openai" else "audio/wav"


def synthesize(text: str) -> AsyncIterator[bytes]:
    if config.TTS_PROVIDER == "openai":
        return openai_tts(text)
    return mock_tts(text)
