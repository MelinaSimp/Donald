"""Reference FastAPI integration: where each `security/` primitive wires in.

This is an *illustrative* agent service. It is intentionally tiny -- the point
is to show the SEAMS, not to be a real agent. Every security module from the
library appears at the place it belongs in a request's lifecycle:

    startup            -> startup_guard.assert_safe_startup
    every response     -> http_headers.security_headers  (CSP report-only)
    auth (HTTP + WS)   -> auth_ratelimit.AuthRateLimiter + bearer_auth.BearerVerifier
    ingest endpoint    -> injection_gate.gate  (untrusted text -> tagged envelope)
    tool dispatch      -> killswitch -> anomaly -> approval -> run -> log_redact
    subprocess in tool -> subprocess_env.shell_minimal
    observability      -> /api/security/status, POST /api/security/audit
    CSP reports        -> POST /api/security/csp-report

Run it::

    pip install fastapi uvicorn
    AGENT_BEARER_TOKEN=dev-token uvicorn examples.fastapi_agent:app --port 8000
    curl -H "Authorization: Bearer dev-token" -X POST localhost:8000/api/tool \\
         -d '{"name":"shell","command":"git status"}' -H 'content-type: application/json'

Nothing here stores secrets or binds a public port by itself.
"""

from __future__ import annotations

import logging
import os
import subprocess
from typing import Optional

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request, Response

from security.anomaly import AnomalyGate
from security.approval import ApprovalGate, hardline_pattern_count
from security.audit import SecurityState, compute_audit
from security.auth_ratelimit import AuthRateLimiter, client_ip
from security.bearer_auth import BearerVerifier, extract_bearer
from security.http_headers import csp_status, security_headers
from security.injection_gate import gate
from security.killswitch import is_active, kill_switch_response
from security.log_redact import redact
from security.startup_guard import assert_safe_startup
from security.subprocess_env import shell_minimal

log = logging.getLogger("agent")

# --- Config (read once; real apps read from a settings object / secrets mgr) ---
DEV_MODE = os.environ.get("AGENT_DEV_MODE", "false").lower() in {"1", "true", "yes", "on"}
BIND_HOST = os.environ.get("AGENT_BIND_HOST", "127.0.0.1")
BEARER_CURRENT = os.environ.get("AGENT_BEARER_TOKEN", "dev-token")
BEARER_PREV = os.environ.get("AGENT_BEARER_TOKEN_PREV") or None
APPROVAL_MODE = os.environ.get("AGENT_APPROVAL_MODE", "smart")
CSP_REPORT_ONLY = os.environ.get("AGENT_CSP_REPORT_ONLY", "true").lower() != "false"

# 1.5 -- refuse to boot dev_mode + public bind. Raises before serving traffic.
assert_safe_startup(dev_mode=DEV_MODE, bind_host=BIND_HOST)

# Shared, process-lifetime security objects.
_limiter = AuthRateLimiter()                                    # 1.4
_verifier = BearerVerifier(current=BEARER_CURRENT, previous=BEARER_PREV)  # 2.1
_anomaly = AnomalyGate()                                        # 3.2
# 3.1 -- mode read live via callable so a settings toggle takes effect at once.
_approval = ApprovalGate(mode=lambda: os.environ.get("AGENT_APPROVAL_MODE", APPROVAL_MODE))

app = FastAPI(title="example-agent")


# --- 2.2 -- security headers + CSP on every response -------------------------
@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    for name, value in security_headers(report_only=CSP_REPORT_ONLY).items():
        response.headers[name] = value
    return response


# --- 1.4 + 2.1 -- auth dependency (same logic guards the WS upgrade) ---------
def require_auth(request: Request, authorization: Optional[str] = Header(default=None)) -> None:
    ip = client_ip(dict(request.headers), request.client.host if request.client else "unknown")

    allowed, retry_after = _limiter.check(ip)          # check rate FIRST
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="rate limited",
            headers={"Retry-After": str(int(retry_after))},
        )

    if not _verifier.is_valid(extract_bearer(authorization)):
        _limiter.record_fail(ip)                       # record on failure
        raise HTTPException(status_code=401, detail="unauthorized")

    _limiter.record_success(ip)                        # clear counters on success


# --- The tool dispatcher: the heart of the seam ------------------------------
def dispatch_tool(name: str, command: str = "") -> dict:
    """killswitch -> anomaly cap -> approval gate -> run -> redacted logging."""
    # 3.3 -- kill switch short-circuits everything.
    if is_active():
        return kill_switch_response(agent_name="example-agent")

    # 3.2 -- per-tool frequency cap.
    cap = _anomaly.check_and_record(name)
    if cap["status"] == "anomaly_gate_blocked":
        return cap

    # 3.1 -- tiered approval for code-exec tools (hardline always enforced).
    if name in {"shell", "run_code"}:
        decision = _approval.evaluate(command, confirmed=False)
        if not decision.allowed:
            return decision.to_response()              # blocked / confirmation_required

        # 1.3 -- run the subprocess with a stripped env (no secrets leak).
        proc = subprocess.run(
            ["/bin/sh", "-c", command],
            env=shell_minimal(),
            capture_output=True,
            text=True,
            timeout=30,
        )
        result = {"status": "ok", "stdout": proc.stdout, "exit": proc.returncode}
    else:
        result = {"status": "ok", "echo": command}

    # 1.1 -- redact before logging the tool result.
    log.info("tool %s -> %s", name, redact(result))
    return result


@app.post("/api/tool", dependencies=[Depends(require_auth)])
def run_tool(payload: dict = Body(...)) -> dict:
    return dispatch_tool(payload.get("name", ""), payload.get("command", ""))


# --- 1.2 -- ingest endpoint: untrusted text -> tagged, scanned envelope ------
@app.post("/api/ingest", dependencies=[Depends(require_auth)])
def ingest(payload: dict = Body(...)) -> dict:
    gated = gate(payload.get("content", ""), source=payload.get("source", "web_fetch"))
    # In a real agent, gated.to_prompt() is what you embed in the LLM prompt.
    return {
        "flagged": gated.flagged,
        "reasons": gated.flag_reasons,
        "prompt_fragment": gated.to_prompt(),
    }


# --- 3.5 -- the security shield ---------------------------------------------
def _current_state() -> SecurityState:
    return SecurityState(
        kill_switch_active=is_active(),
        llm_api_key_set=bool(os.environ.get("ANTHROPIC_API_KEY")),
        bearer_token_set=bool(BEARER_CURRENT),
        approval_mode=_approval.mode,
        dev_mode=DEV_MODE,
        bind_host=BIND_HOST,
        gate_paths_total=2,          # /api/ingest + structured rows (declared)
        gate_paths_covered=2,
        log_redaction_active=True,
        subprocess_envs_stripped=True,
        hardline_pattern_count=hardline_pattern_count(),
        csp_status=csp_status(report_only=CSP_REPORT_ONLY),
        csrf_origin_gate=False,      # not implemented in this minimal example
    )


@app.get("/api/security/status")
def security_status() -> dict:
    return compute_audit(_current_state())


@app.post("/api/security/audit", dependencies=[Depends(require_auth)])
def run_audit() -> dict:
    return compute_audit(_current_state())


# --- 2.2 -- CSP violation sink ----------------------------------------------
@app.post("/api/security/csp-report")
async def csp_report(request: Request) -> Response:
    body = await request.body()
    log.warning("csp-violation: %s", redact(body.decode("utf-8", "replace"), max_len=1000))
    return Response(status_code=204)
