"""Agent Security Hardening library.

A framework-agnostic, dependency-free toolkit of the load-bearing security
primitives an AI-agent codebase needs: untrusted-content gating, log
redaction, subprocess env stripping, tiered command approval with an
immutable hardline blocklist, per-tool anomaly caps, a kill switch, auth
rate-limiting, bearer-token rotation, HTTP security headers, CVE scanning,
and a self-audit "security shield" that surfaces drift.

Every module is pure standard-library Python and returns plain data, so it
drops into FastAPI, Flask, Starlette, aiohttp, a bare WSGI app, or a CLI
without pulling in a web framework.

Threat model (see README) numbering is referenced in each module's
docstring as T1..T7.
"""

__version__ = "0.1.0"

from . import (  # noqa: F401
    anomaly,
    approval,
    audit,
    auth_ratelimit,
    bearer_auth,
    cve_scan,
    http_headers,
    injection_gate,
    killswitch,
    log_redact,
    startup_guard,
    subprocess_env,
)

__all__ = [
    "anomaly",
    "approval",
    "audit",
    "auth_ratelimit",
    "bearer_auth",
    "cve_scan",
    "http_headers",
    "injection_gate",
    "killswitch",
    "log_redact",
    "startup_guard",
    "subprocess_env",
]
