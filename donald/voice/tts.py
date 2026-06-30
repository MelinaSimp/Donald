"""Tier 2 — text-to-speech via ElevenLabs (HTTP API).

We request raw 16 kHz PCM (``output_format=pcm_16000``) so the audio plays
straight through sounddevice with no mp3 decoding step.
"""

from __future__ import annotations

import httpx

from ..config import Config

PCM_SAMPLE_RATE = 16000


class ElevenLabsTTS:
    def __init__(self, config: Config):
        if not config.elevenlabs_api_key:
            raise RuntimeError(
                "ELEVENLABS_API_KEY is not set — needed for speech-out."
            )
        self.api_key = config.elevenlabs_api_key
        self.voice_id = config.elevenlabs_voice_id

    def synthesize(self, text: str) -> bytes:
        """Return raw signed-16-bit mono PCM at 16 kHz for the given text."""
        if not text.strip():
            return b""
        url = (
            f"https://api.elevenlabs.io/v1/text-to-speech/{self.voice_id}"
            f"?output_format=pcm_{PCM_SAMPLE_RATE}"
        )
        try:
            r = httpx.post(
                url,
                headers={
                    "xi-api-key": self.api_key,
                    "Content-Type": "application/json",
                },
                json={
                    "text": text,
                    "model_id": "eleven_turbo_v2_5",
                    "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
                },
                timeout=30,
            )
            r.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"ElevenLabs synthesis failed: {exc}")
        return r.content
