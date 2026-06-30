"""Tier 2 — speech-to-text via Deepgram (HTTP API).

We call Deepgram's prerecorded ``/v1/listen`` endpoint directly with httpx, so
there's no SDK version to track. Give it WAV bytes, get a transcript back.
"""

from __future__ import annotations

import httpx

from ..config import Config


class DeepgramSTT:
    ENDPOINT = "https://api.deepgram.com/v1/listen"

    def __init__(self, config: Config):
        if not config.deepgram_api_key:
            raise RuntimeError(
                "DEEPGRAM_API_KEY is not set — needed for speech-to-text."
            )
        self.api_key = config.deepgram_api_key

    def transcribe(self, wav_bytes: bytes) -> str:
        if not wav_bytes:
            return ""
        try:
            r = httpx.post(
                self.ENDPOINT,
                params={"model": "nova-2", "smart_format": "true", "punctuate": "true"},
                headers={
                    "Authorization": f"Token {self.api_key}",
                    "Content-Type": "audio/wav",
                },
                content=wav_bytes,
                timeout=30,
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"Deepgram transcription failed: {exc}")

        data = r.json()
        try:
            return (
                data["results"]["channels"][0]["alternatives"][0]["transcript"]
            ).strip()
        except (KeyError, IndexError):
            return ""
