"""Central settings for Prism: models, cost caps, env access.

Everything that varies per deployment (which model plans, which model composes,
the per-task cost ceiling, the serving prefix, which env vars are present) is
read here so the rest of the package never touches ``os.environ`` ad hoc.

No external dependency is imported at module load. Keys are *read* here but their
absence is never fatal at import time — only the live call path that needs a key
raises, and it raises with a clear message.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Model defaults
# ---------------------------------------------------------------------------
#
# The planning loop is cheap/fast (Sonnet-class). The *composition* step shells
# out to Claude Code, which can run the same or a stronger model — it does the
# actual building. Both are overridable via env.

DEFAULT_PLANNING_MODEL = "claude-sonnet-4-6"
DEFAULT_COMPOSER_MODEL = "claude-sonnet-4-6"

# Gemini image models (Tier 5). Standard is GA; premium is preview.
IMAGE_MODEL_STANDARD = "gemini-2.5-flash-image"
IMAGE_MODEL_PREMIUM = "gemini-3-pro-image-preview"
IMAGE_COST_STANDARD_USD = 0.04
IMAGE_COST_PREMIUM_USD = 0.12

# Env vars the Claude Code subprocess is allowed to inherit. Everything else
# (other secrets) is blocked from leaking into the child (see claude_code_runner).
CHILD_ENV_ALLOWLIST = ("ANTHROPIC_API_KEY", "HOME", "PATH", "USER", "LANG", "TMPDIR")


@dataclass(frozen=True)
class Settings:
    planning_model: str = DEFAULT_PLANNING_MODEL
    composer_model: str = DEFAULT_COMPOSER_MODEL
    # Hard ceiling per dispatch. Advisory in this harness (we don't meter tokens
    # mid-run), but surfaced everywhere so a caller can enforce it.
    cost_cap_usd: float = 6.0
    # Claude Code turn budget per compose.
    composer_max_turns: int = 40
    image_model_standard: str = IMAGE_MODEL_STANDARD
    image_model_premium: str = IMAGE_MODEL_PREMIUM

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            planning_model=os.environ.get("PRISM_PLANNING_MODEL", DEFAULT_PLANNING_MODEL),
            composer_model=os.environ.get("PRISM_COMPOSER_MODEL", DEFAULT_COMPOSER_MODEL),
            cost_cap_usd=float(os.environ.get("PRISM_COST_CAP_USD", "6.0")),
            composer_max_turns=int(os.environ.get("PRISM_COMPOSER_MAX_TURNS", "40")),
        )


# ---------------------------------------------------------------------------
# Key presence (never raises) — used to decide live vs. degraded behavior
# ---------------------------------------------------------------------------


def anthropic_api_key() -> str | None:
    return os.environ.get("ANTHROPIC_API_KEY") or None


def gemini_api_key() -> str | None:
    # Accept either common name.
    return os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY") or None


def have_anthropic_key() -> bool:
    return anthropic_api_key() is not None


def have_gemini_key() -> bool:
    return gemini_api_key() is not None


@dataclass
class MissingDependency(RuntimeError):
    """A live integration was invoked without its dependency or key present."""

    message: str = ""

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.message
