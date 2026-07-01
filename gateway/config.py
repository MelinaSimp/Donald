"""Environment-driven configuration for the Donald gateway.

Every knob is an environment variable so nothing secret lives in the repo.
``load_settings()`` reads the process environment once at startup and returns
an immutable ``Settings``. See ``gateway/.env.example`` for the full list.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List, Optional


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_list(name: str, default: List[str]) -> List[str]:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return list(default)
    return [item.strip() for item in raw.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    """Resolved gateway configuration."""

    # --- Donald brain (Anthropic) ---
    anthropic_api_key: Optional[str]
    donald_model: str
    donald_max_tokens: int
    donald_temperature: float

    # --- Hermes (local agent) ---
    # mode="http": talk to an OpenAI-compatible Hermes API server.
    # mode="cli":  drive Hermes' one-shot CLI (optionally via `docker exec`).
    hermes_mode: str
    hermes_base_url: str
    hermes_api_key: Optional[str]
    hermes_model: str
    hermes_timeout_s: float
    # CLI-mode knobs (ignored in http mode):
    hermes_docker_container: Optional[str]
    hermes_cli_path: str
    hermes_cli_extra_args: List[str]

    # --- Voice (ElevenLabs TTS) ---
    voice_enabled: bool
    elevenlabs_api_key: Optional[str]
    elevenlabs_voice_id: str
    elevenlabs_model: str

    # --- Gateway server ---
    host: str
    port: int
    cors_origins: List[str] = field(default_factory=list)

    @property
    def hermes_configured(self) -> bool:
        return bool(self.hermes_base_url)

    @property
    def voice_configured(self) -> bool:
        return self.voice_enabled and bool(self.elevenlabs_api_key)

    def redacted(self) -> dict:
        """A safe-to-log view: presence of secrets, never their values."""
        return {
            "donald_model": self.donald_model,
            "anthropic_api_key": bool(self.anthropic_api_key),
            "hermes_mode": self.hermes_mode,
            "hermes_base_url": self.hermes_base_url,
            "hermes_api_key": bool(self.hermes_api_key),
            "hermes_model": self.hermes_model,
            "hermes_docker_container": self.hermes_docker_container,
            "voice_enabled": self.voice_enabled,
            "elevenlabs_api_key": bool(self.elevenlabs_api_key),
            "elevenlabs_voice_id": self.elevenlabs_voice_id,
            "host": self.host,
            "port": self.port,
            "cors_origins": self.cors_origins,
        }


def load_settings() -> Settings:
    """Build ``Settings`` from the current process environment."""
    return Settings(
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
        donald_model=os.environ.get("DONALD_MODEL", "claude-opus-4-8"),
        donald_max_tokens=_env_int("DONALD_MAX_TOKENS", 1024),
        donald_temperature=float(os.environ.get("DONALD_TEMPERATURE", "0.8")),
        hermes_mode=os.environ.get("HERMES_MODE", "http").strip().lower(),
        # Hermes defaults match its API server: 127.0.0.1:8642, OpenAI-compatible.
        hermes_base_url=os.environ.get("HERMES_BASE_URL", "http://127.0.0.1:8642"),
        hermes_api_key=os.environ.get("HERMES_API_KEY"),
        hermes_model=os.environ.get("HERMES_MODEL", "hermes"),
        # Local models can be slow (cold-load + tool loops); default generous.
        hermes_timeout_s=float(os.environ.get("HERMES_TIMEOUT_S", "300")),
        hermes_docker_container=os.environ.get("HERMES_DOCKER_CONTAINER") or None,
        hermes_cli_path=os.environ.get(
            "HERMES_CLI_PATH", "/opt/hermes/.venv/bin/hermes"
        ),
        hermes_cli_extra_args=_env_list("HERMES_CLI_EXTRA_ARGS", ["--yolo"]),
        voice_enabled=_env_bool("VOICE_ENABLED", False),
        elevenlabs_api_key=os.environ.get("ELEVENLABS_API_KEY"),
        # Default is Donald's voice; override per-deployment if you reclone it.
        elevenlabs_voice_id=os.environ.get("ELEVENLABS_VOICE_ID", "DAqNbWkj293fwKQlkwBq"),
        elevenlabs_model=os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
        host=os.environ.get("GATEWAY_HOST", "127.0.0.1"),
        port=_env_int("GATEWAY_PORT", 8765),
        cors_origins=_env_list("GATEWAY_CORS_ORIGINS", ["*"]),
    )
