"""Mouth — text-to-speech (ElevenLabs), behind a seam.

One job: give me text, play it aloud. ElevenLabs streams audio, so playback can
start before the whole sentence is synthesized — what makes Wren feel responsive
rather than laggy. The voice id lives in config.yaml (voice.elevenlabs_voice_id),
not in code. The key lives in ELEVENLABS_API_KEY.

Playback runs in a thread so the caller can interrupt it (Tier 3: let me cut it
off) by calling stop().
"""
from __future__ import annotations

import threading
from typing import Protocol


class TTS(Protocol):
    def speak(self, text: str) -> None: ...
    def stop(self) -> None: ...


class ElevenLabsTTS:
    def __init__(self, api_key: str, voice_id: str, model: str = "eleven_turbo_v2_5"):
        if not api_key:
            raise RuntimeError("Missing ELEVENLABS_API_KEY (set it in .env).")
        if not voice_id:
            raise RuntimeError(
                "No ElevenLabs voice chosen. Set voice.elevenlabs_voice_id in config.yaml."
            )
        self.api_key = api_key
        self.voice_id = voice_id
        self.model = model
        self._client = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def _client_lazy(self):
        if self._client is None:
            from elevenlabs.client import ElevenLabs

            self._client = ElevenLabs(api_key=self.api_key)
        return self._client

    def speak(self, text: str) -> None:
        """Synthesize and play `text`, blocking until done or stop() is called."""
        from elevenlabs import stream as play_stream

        self._stop.clear()
        client = self._client_lazy()
        audio = client.text_to_speech.stream(
            text=text, voice_id=self.voice_id, model_id=self.model
        )

        def gen():
            for chunk in audio:
                if self._stop.is_set():
                    break
                yield chunk

        play_stream(gen())

    def speak_async(self, text: str) -> None:
        self._thread = threading.Thread(target=self.speak, args=(text,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)


def build_tts(config) -> ElevenLabsTTS:
    return ElevenLabsTTS(
        api_key=config.secret("ELEVENLABS_API_KEY", required=True),
        voice_id=config.get("voice.elevenlabs_voice_id", ""),
        model=config.get("voice.elevenlabs_model", "eleven_turbo_v2_5"),
    )
