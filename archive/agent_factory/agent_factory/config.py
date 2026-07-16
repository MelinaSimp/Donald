"""Runtime configuration for the Factory.

Everything the Factory needs to know about *this* host install lives here:
where the database is, where spec markdown gets written, which models to
use, the reserved-slug set, the daily spawn cap, and the revision-round
limit. Values come from environment variables with sensible defaults so a
fresh checkout runs with zero config.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

# Models. Defaults target the latest capable Claude tier; override per-env.
DEFAULT_RESEARCH_MODEL = os.environ.get("FACTORY_RESEARCH_MODEL", "claude-sonnet-4-5")
DEFAULT_PROMPT_MODEL = os.environ.get("FACTORY_PROMPT_MODEL", "claude-sonnet-4-5")
DEFAULT_AGENT_MODEL = os.environ.get("FACTORY_AGENT_MODEL", "claude-sonnet-4-5")

# Slugs the Factory must never mint. The Factory itself is reserved so it can
# never clone itself. Populate with your existing specialists' slugs.
DEFAULT_RESERVED_SLUGS = frozenset({"factory", "forge", "admin", "system", "root"})


@dataclass
class Config:
    """Resolved host configuration."""

    db_path: Path
    specs_dir: Path
    research_model: str = DEFAULT_RESEARCH_MODEL
    prompt_model: str = DEFAULT_PROMPT_MODEL
    agent_model: str = DEFAULT_AGENT_MODEL
    reserved_slugs: frozenset[str] = DEFAULT_RESERVED_SLUGS
    daily_cap: int = 5  # max spawn tasks per user per day
    max_revision_iterations: int = 3  # reject-with-feedback rounds before auto-fail
    research_cache_hours: int = 24
    research_max_iters: int = 8
    agent_max_iters: int = 8

    @classmethod
    def load(cls) -> "Config":
        root = Path(os.environ.get("FACTORY_HOME", Path.cwd())).resolve()
        db_path = Path(os.environ.get("FACTORY_DB", root / "factory.db"))
        specs_dir = Path(os.environ.get("FACTORY_SPECS_DIR", root / "agent-specs"))
        cfg = cls(db_path=db_path, specs_dir=specs_dir)
        if os.environ.get("FACTORY_DAILY_CAP"):
            cfg.daily_cap = int(os.environ["FACTORY_DAILY_CAP"])
        if os.environ.get("FACTORY_MAX_REVISIONS"):
            cfg.max_revision_iterations = int(os.environ["FACTORY_MAX_REVISIONS"])
        extra = os.environ.get("FACTORY_RESERVED_SLUGS", "")
        if extra:
            cfg.reserved_slugs = DEFAULT_RESERVED_SLUGS | {
                s.strip() for s in extra.split(",") if s.strip()
            }
        return cfg
