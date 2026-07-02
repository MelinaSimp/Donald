"""Donald's configuration — sensible defaults, overridable without code changes.

Settings come from three places, later ones winning:
1. The defaults below.
2. A JSON file at ``~/.donald/config.json`` (any subset of keys).
3. Environment variables (``DONALD_MODEL``, ``DONALD_SHELL_TIMEOUT``, …).

Everything has a safe default, so a missing or malformed config file never
stops Donald from starting — it just falls back.
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass, fields, replace

CONFIG_PATH = pathlib.Path.home() / ".donald" / "config.json"


@dataclass(frozen=True)
class Config:
    model: str = "claude-opus-4-8"
    max_tokens: int = 4096
    shell_timeout_s: int = 60
    max_output_chars: int = 100_000
    # Command prefixes Donald may run WITHOUT asking. Empty by default: every
    # shell command is approved by hand until you opt specific ones in (e.g.
    # ["git status", "ls", "cat"]). Match is a plain prefix on the command.
    shell_auto_approve: tuple[str, ...] = ()
    # Start with voice output on. Off by default; needs the `voice` extra.
    voice: bool = False


def _from_file() -> dict:
    if not CONFIG_PATH.is_file():
        return {}
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}  # malformed config should never block startup
    return data if isinstance(data, dict) else {}


def _coerce(field_name: str, raw: str, current):
    """Turn an env-var string into the type the field expects."""
    if isinstance(current, bool):
        return raw.strip().lower() in ("1", "true", "yes", "on")
    if isinstance(current, int):
        try:
            return int(raw)
        except ValueError:
            return current
    if isinstance(current, tuple):
        return tuple(p.strip() for p in raw.split(",") if p.strip())
    return raw


_ENV_KEYS = {
    "DONALD_MODEL": "model",
    "DONALD_MAX_TOKENS": "max_tokens",
    "DONALD_SHELL_TIMEOUT": "shell_timeout_s",
    "DONALD_MAX_OUTPUT_CHARS": "max_output_chars",
    "DONALD_SHELL_AUTO_APPROVE": "shell_auto_approve",
    "DONALD_VOICE": "voice",
}


def load() -> Config:
    """Build the effective config: defaults < config file < environment."""
    cfg = Config()

    # Layer 2: config file. Ignore unknown keys; keep known ones type-correct.
    file_data = _from_file()
    known = {f.name for f in fields(cfg)}
    updates = {}
    for key, value in file_data.items():
        if key not in known:
            continue
        if key == "shell_auto_approve" and isinstance(value, list):
            value = tuple(str(v) for v in value)
        updates[key] = value
    if updates:
        cfg = replace(cfg, **updates)

    # Layer 3: environment variables.
    env_updates = {}
    for env_key, attr in _ENV_KEYS.items():
        raw = os.environ.get(env_key)
        if raw is not None:
            env_updates[attr] = _coerce(attr, raw, getattr(cfg, attr))
    if env_updates:
        cfg = replace(cfg, **env_updates)

    return cfg


def shell_auto_approved(command: str, cfg: Config) -> bool:
    """True if `command` matches one of the configured auto-approve prefixes."""
    stripped = command.strip()
    return any(stripped.startswith(prefix) for prefix in cfg.shell_auto_approve)
