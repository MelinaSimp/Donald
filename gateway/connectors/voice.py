"""ElevenLabs text-to-speech connector — Donald's voice.

Turns Donald's reply text into spoken audio using ElevenLabs. The voice is
chosen by ``ELEVENLABS_VOICE_ID`` (point it at your cloned Trump-style voice).
Returns raw MP3 bytes; the gateway base64-encodes them and ships them to the
UI, which plays them. Speech-to-text (the mic side) is handled in Hermes / the
browser, so this connector is TTS-only by design.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

_ELEVENLABS_BASE = "https://api.elevenlabs.io/v1/text-to-speech"


@dataclass
class VoiceResult:
    ok: bool
    audio: bytes = b""
    mime: str = "audio/mpeg"
    error: Optional[str] = None


class ElevenLabsVoice:
    """Minimal ElevenLabs TTS client."""

    name = "elevenlabs"

    def __init__(
        self,
        api_key: Optional[str],
        voice_id: str,
        model: str = "eleven_multilingual_v2",
        timeout_s: float = 60.0,
        client: Optional[object] = None,
    ) -> None:
        self.api_key = api_key
        self.voice_id = voice_id
        self.model = model
        self.timeout_s = timeout_s
        self._client = client

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.voice_id)

    def _get_client(self):
        if self._client is None:
            import httpx  # imported lazily so the dep is optional until used

            self._client = httpx.AsyncClient(timeout=self.timeout_s)
        return self._client

    async def synthesize(self, text: str) -> VoiceResult:
        """Render ``text`` to MP3 audio bytes."""
        if not self.configured:
            return VoiceResult(
                ok=False,
                error="ElevenLabs not configured (set ELEVENLABS_API_KEY and "
                "ELEVENLABS_VOICE_ID)",
            )
        if not text.strip():
            return VoiceResult(ok=False, error="nothing to speak")

        client = self._get_client()
        payload = {
            "text": text,
            "model_id": self.model,
            "voice_settings": {"stability": 0.4, "similarity_boost": 0.85},
        }
        headers = {
            "xi-api-key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        try:
            resp = await client.post(
                f"{_ELEVENLABS_BASE}/{self.voice_id}",
                headers=headers,
                json=payload,
            )
        except Exception as exc:
            return VoiceResult(ok=False, error=f"ElevenLabs request failed: {exc}")

        if resp.status_code >= 400:
            return VoiceResult(
                ok=False,
                error=f"ElevenLabs HTTP {resp.status_code}: {_safe_text(resp)}",
            )
        return VoiceResult(ok=True, audio=resp.content, mime="audio/mpeg")

    async def aclose(self) -> None:
        if self._client is not None and hasattr(self._client, "aclose"):
            await self._client.aclose()


def _safe_text(resp) -> str:
    try:
        return resp.text[:300]
    except Exception:
        return "<unreadable body>"
