"""Configuration + secrets loading.

Config knobs come from config.yaml (Tier 6: tune behaviour without code edits).
Secrets come from the environment / a git-ignored .env file (Tier 1: keys never
live in source).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

# Round-trip loader: comments and formatting in config.yaml survive programmatic
# edits (the kill switch and change_settings flip one value, leaving the
# documented file intact).
_yaml = YAML()
_yaml.preserve_quotes = True
_yaml.indent(mapping=2, sequence=2, offset=0)

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = ROOT / "config.yaml"
ENV_PATH = ROOT / ".env"


def _load_dotenv(path: Path = ENV_PATH) -> None:
    """Minimal .env loader so we don't add a dependency. Real environment
    variables already set always win over .env values."""
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip("'\"")
        os.environ.setdefault(key, value)


class Config:
    """Thin wrapper over the parsed YAML with dotted lookups and sensible
    defaults, plus secret access from the environment."""

    def __init__(self, data: dict[str, Any], path: Path):
        self._data = data
        self.path = path

    @classmethod
    def load(cls, path: Path | str = DEFAULT_CONFIG_PATH) -> "Config":
        _load_dotenv()
        path = Path(path)
        data = _yaml.load(path.read_text()) if path.exists() else {}
        return cls(data or {}, path)

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        """Set a value and persist back to config.yaml. Used by the
        change_settings tool and the kill switch — both gated/auditable."""
        node = self._data
        parts = dotted.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
        self.save()

    def save(self) -> None:
        with self.path.open("w") as f:
            _yaml.dump(self._data, f)

    # --- secrets -----------------------------------------------------------
    @staticmethod
    def secret(name: str, required: bool = False) -> str | None:
        val = os.environ.get(name)
        if required and not val:
            raise RuntimeError(
                f"Missing secret {name}. Copy .env.example to .env and set it."
            )
        return val

    def resolve_path(self, dotted: str, default: str) -> Path:
        """Resolve a config path relative to the project root."""
        rel = self.get(dotted, default)
        p = Path(rel)
        return p if p.is_absolute() else ROOT / p
