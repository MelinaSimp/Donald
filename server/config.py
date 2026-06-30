from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Auth
    bearer_token: str

    # APIs
    anthropic_api_key: str
    deepgram_api_key: str
    elevenlabs_api_key: str

    # Optional: Google APIs (stubbed if not provided)
    google_calendar_credentials_json: str = ""
    gmail_credentials_json: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = False

    # Database
    db_path: str = "donald.db"

    # TTS
    tts_cache_ttl_seconds: int = 300

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
"""Runtime configuration, all overridable via environment variables."""

from __future__ import annotations

import os


# --- LLM ---------------------------------------------------------------------
# Default to the latest, most capable Claude model. For a voice agent, LLM
# time-to-first-token matters more than raw throughput, so a faster tier
# (e.g. claude-haiku-4-5 or claude-sonnet-4-6) is a reasonable swap once you
# have measured the new latency floor — set LLM_MODEL to change it.
LLM_MODEL = os.environ.get("LLM_MODEL", "claude-opus-4-8")
LLM_MAX_TOKENS = int(os.environ.get("LLM_MAX_TOKENS", "1024"))
LLM_SYSTEM = os.environ.get(
    "LLM_SYSTEM",
    "You are a friendly voice assistant. Keep replies conversational and "
    "concise — a few short sentences. Each sentence is spoken aloud the "
    "instant you finish it, so write in complete, self-contained sentences.",
)

# Use the mock LLM (no API key, deterministic) when ANTHROPIC_API_KEY is unset
# or USE_MOCK_LLM=1. This is what lets the project run and be tested offline.
USE_MOCK_LLM = (
    os.environ.get("USE_MOCK_LLM") == "1"
    or not os.environ.get("ANTHROPIC_API_KEY")
)

# --- TTS ---------------------------------------------------------------------
# "mock" (offline, silent WAV), or "openai" (streaming MP3 via OpenAI TTS).
TTS_PROVIDER = os.environ.get("TTS_PROVIDER", "mock")
OPENAI_TTS_MODEL = os.environ.get("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
OPENAI_TTS_VOICE = os.environ.get("OPENAI_TTS_VOICE", "alloy")

# How long a segment's text stays available for its TTS fetch.
SEGMENT_TTL_S = float(os.environ.get("SEGMENT_TTL_S", "120"))

# --- VAD ---------------------------------------------------------------------
# Silence (in ms) required before deciding "the user is done". 800-1000ms is
# the usual sweet spot for English conversational speech. This reference takes
# typed input, so the value is advisory/echoed only — wire it into your STT or
# client-side VAD. Note any STT-provider endpointing window composes with this.
VAD_SILENCE_MS = int(os.environ.get("VAD_SILENCE_MS", "900"))
