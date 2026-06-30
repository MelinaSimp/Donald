"""Reference Postgres connection layer for a Python + FastAPI app.

Drop this into your real app (e.g. app/db.py) and adapt the imports. The point
is the local<->cloud flag: flip DB_MODE to switch instantly, with zero hard-coded
credentials.

    DB_MODE=local   -> uses your existing local Postgres (fallback / rollback)
    DB_MODE=cloud   -> uses the DigitalOcean droplet with sslmode=require

Nothing here is secret: every credential is read from the environment. See
examples/.env.example for the variables.
"""
from __future__ import annotations

import os
from functools import lru_cache
from urllib.parse import quote_plus


class DatabaseConfigError(RuntimeError):
    """Raised when required env vars for the selected DB_MODE are missing."""


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        raise DatabaseConfigError(
            f"Environment variable {name!r} is required for DB_MODE="
            f"{os.environ.get('DB_MODE', 'local')!r}. See examples/.env.example."
        )
    return val


@lru_cache(maxsize=1)
def database_url() -> str:
    """Build the Postgres DSN from environment variables.

    Local mode keeps your old connection working so you can roll back instantly.
    Cloud mode targets the droplet and always enforces TLS (sslmode=require).
    """
    mode = os.environ.get("DB_MODE", "local").lower()

    if mode == "local":
        # Your pre-migration local connection. Defaults match a typical local dev box.
        host = os.environ.get("LOCAL_DB_HOST", "localhost")
        port = os.environ.get("LOCAL_DB_PORT", "5432")
        name = os.environ.get("LOCAL_DB_NAME", "assistant")
        user = os.environ.get("LOCAL_DB_USER", os.environ.get("USER", "postgres"))
        password = os.environ.get("LOCAL_DB_PASSWORD", "")
        sslmode = os.environ.get("LOCAL_DB_SSLMODE", "disable")
        auth = quote_plus(user) + (f":{quote_plus(password)}" if password else "")
        return f"postgresql://{auth}@{host}:{port}/{name}?sslmode={sslmode}"

    if mode == "cloud":
        host = _require("CLOUD_DB_HOST")          # droplet public IP
        port = os.environ.get("CLOUD_DB_PORT", "5432")
        name = _require("CLOUD_DB_NAME")
        user = _require("CLOUD_DB_USER")
        password = _require("CLOUD_DB_PASSWORD")  # from your password manager / secret store
        # Self-signed cert on a bare IP -> 'require' (encrypt, don't verify CN).
        # If you later add a domain + Let's Encrypt, bump to 'verify-full'.
        sslmode = os.environ.get("CLOUD_DB_SSLMODE", "require")
        auth = f"{quote_plus(user)}:{quote_plus(password)}"
        return f"postgresql://{auth}@{host}:{port}/{name}?sslmode={sslmode}"

    raise DatabaseConfigError(f"Unknown DB_MODE={mode!r}; expected 'local' or 'cloud'.")


def async_database_url() -> str:
    """Same DSN with the asyncpg driver prefix, for SQLAlchemy async / databases lib."""
    return database_url().replace("postgresql://", "postgresql+asyncpg://", 1)


# --- Example wiring (uncomment what matches your stack) ----------------------
#
# SQLAlchemy (async):
#   from sqlalchemy.ext.asyncio import create_async_engine
#   engine = create_async_engine(async_database_url(), pool_pre_ping=True)
#
# asyncpg pool:
#   import asyncpg
#   pool = await asyncpg.create_pool(dsn=database_url())
#
# psycopg (sync):
#   import psycopg
#   conn = psycopg.connect(database_url())
