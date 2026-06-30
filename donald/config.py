"""Central configuration for Donald.

Everything Donald needs to know about its environment lives here, loaded once
from environment variables (and a local ``.env`` if present). Each tier reads
the fields it needs; nothing here forces you to configure tiers you aren't
using yet.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:  # python-dotenv is a hard dependency, but degrade gracefully if missing.
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # pragma: no cover - only hit if dotenv is absent
    pass


def _path(env_value: str | None, default: Path) -> Path:
    return Path(env_value).expanduser() if env_value else default


@dataclass
class Config:
    # ── Brain (Tier 0/1) ────────────────────────────────────────────────
    brain: str  # "claude" or "mock"
    model: str
    anthropic_api_key: str | None

    # ── Voice (Tier 2) ──────────────────────────────────────────────────
    deepgram_api_key: str | None
    elevenlabs_api_key: str | None
    elevenlabs_voice_id: str

    # ── Web search (Tier 1) ─────────────────────────────────────────────
    brave_api_key: str | None

    # ── Storage / safety ────────────────────────────────────────────────
    db_path: Path
    workspace: Path

    # ── Proactive (Tier 4) ──────────────────────────────────────────────
    proactive_enabled: bool
    proactive_interval: int

    @classmethod
    def load(cls) -> "Config":
        root = Path.cwd()
        brain = os.getenv("DONALD_BRAIN", "claude").strip().lower()
        anthropic_key = os.getenv("ANTHROPIC_API_KEY") or None
        # If they asked for the real brain but have no key, fall back to mock
        # rather than crashing — keeps Tier 0 testable out of the box.
        if brain == "claude" and not anthropic_key:
            brain = "mock"

        return cls(
            brain=brain,
            model=os.getenv("DONALD_MODEL", "claude-opus-4-8"),
            anthropic_api_key=anthropic_key,
            deepgram_api_key=os.getenv("DEEPGRAM_API_KEY") or None,
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY") or None,
            elevenlabs_voice_id=os.getenv(
                "ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM"
            ),
            brave_api_key=os.getenv("BRAVE_API_KEY") or None,
            db_path=_path(
                os.getenv("DONALD_DB_PATH"), root / "donald_data" / "donald.db"
            ),
            workspace=_path(
                os.getenv("DONALD_WORKSPACE"), root / "donald_workspace"
            ),
            proactive_enabled=os.getenv("DONALD_PROACTIVE", "off").strip().lower()
            in {"on", "1", "true", "yes"},
            proactive_interval=int(os.getenv("DONALD_PROACTIVE_INTERVAL", "60")),
        )

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.workspace.mkdir(parents=True, exist_ok=True)


# Personality / system prompt. Kept here so every tier shares one Donald.
SYSTEM_PROMPT = """You are Donald, a personal AI assistant in the spirit of \
Jarvis — capable, concise, and warm. You speak naturally, like a trusted aide, \
not a corporate chatbot. Keep answers short unless asked to go deep.

You have tools. Use them when they help, and say plainly when you cannot do \
something. When you take an action in the real world (files, shell, sending \
things), be careful and confirm anything destructive or irreversible.

When your reply will be spoken aloud, write the way people talk: no markdown, \
no bullet lists, no code blocks — just clear sentences."""
