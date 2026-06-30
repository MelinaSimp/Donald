"""Ears — speech-to-text (Deepgram), behind a seam.

One job: give me audio (WAV bytes), get back text. Swap the transcriber here
without touching the rest of the harness. The key lives in DEEPGRAM_API_KEY,
never in code.
"""
from __future__ import annotations

from typing import Protocol


class STT(Protocol):
    def transcribe(self, wav_bytes: bytes) -> str: ...


class DeepgramSTT:
    def __init__(self, api_key: str, model: str = "nova-2"):
        if not api_key:
            raise RuntimeError("Missing DEEPGRAM_API_KEY (set it in .env).")
        self.api_key = api_key
        self.model = model
        self._client = None

    def _client_lazy(self):
        if self._client is None:
            from deepgram import DeepgramClient

            self._client = DeepgramClient(self.api_key)
        return self._client

    def transcribe(self, wav_bytes: bytes) -> str:
        from deepgram import PrerecordedOptions

        client = self._client_lazy()
        options = PrerecordedOptions(model=self.model, smart_format=True, punctuate=True)
        source = {"buffer": wav_bytes, "mimetype": "audio/wav"}
        resp = client.listen.rest.v("1").transcribe_file(source, options)
        return resp.results.channels[0].alternatives[0].transcript.strip()


def build_stt(config) -> DeepgramSTT:
    return DeepgramSTT(
        api_key=config.secret("DEEPGRAM_API_KEY", required=True),
        model=config.get("voice.deepgram_model", "nova-2"),
    )
