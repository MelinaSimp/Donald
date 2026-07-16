"""Runtime settings, loaded from the environment (Doppler injects these).

Connection strings are NEVER hard-coded. Each read-only Supabase project gets
one ``supabase_<slug>_url`` field here, populated from ``SUPABASE_<SLUG>_URL``.
The value is an asyncpg DSN for the project's ``trillion_analytics`` role.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields
from typing import Mapping


@dataclass
class Settings:
    # asyncpg DSN for trillion_analytics on the donald DB (SUPABASE_DONALD_URL).
    supabase_donald_url: str = ""

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "Settings":
        """Build settings from the environment.

        Every field named ``foo_bar`` is read from the ``FOO_BAR`` env var,
        falling back to the field default when unset. New Supabase projects
        only need a new ``supabase_<slug>_url`` field — no wiring changes here.
        """
        env = os.environ if environ is None else environ
        values = {f.name: env.get(f.name.upper(), f.default) for f in fields(cls)}
        return cls(**values)
