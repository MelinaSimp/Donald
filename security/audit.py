"""3.5 - Self-audit + security-shield score.

Hardening rots without measurement. ``compute_audit(state)`` runs a list of
independent signal functions, each returning ``{name, label, value, delta,
severity, detail}``, sums the deltas onto a 100-point base, clamps to
``[0, 100]``, and maps to a colour (>=85 green, 60-84 amber, <60 red).

Wire ``compute_audit`` behind ``GET /api/security/status`` and a "Run audit
now" ``POST /api/security/audit``; render the score as a shield indicator in
your admin surface and fire an alert when it drops below green.

``SecurityState`` is the single input -- populate it from your live config
(env vars, settings, the persisted CVE record, manual attestation flags).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

SEV_OK = "ok"
SEV_INFO = "info"
SEV_WARNING = "warning"
SEV_CRITICAL = "critical"


@dataclass
class SecurityState:
    """Live snapshot the audit reads. Populate from your real config."""

    # Tier 1 / runtime
    kill_switch_active: bool = False
    llm_api_key_set: bool = True
    bearer_token_set: bool = True
    approval_mode: str = "smart"          # off | smart | manual
    dev_mode: bool = False
    bind_host: str = "127.0.0.1"
    gate_paths_total: int = 0             # known ingest paths
    gate_paths_covered: int = 0          # how many are gated
    log_redaction_active: bool = True
    subprocess_envs_stripped: bool = True
    hardline_pattern_count: int = 0
    # Tier 2
    csp_status: str = "report-only"       # enforcing | report-only | disabled
    csrf_origin_gate: bool = False
    token_scope_audited: bool = False     # manual attestation
    db_readonly_active: bool = False      # manual attestation
    # Tier 3
    cve_record: Optional[Dict[str, object]] = None
    # clock injectable for tests
    now: Callable[[], float] = field(default=time.time)


def _sig(name, label, value, delta, severity, detail=""):
    return {
        "name": name,
        "label": label,
        "value": value,
        "delta": delta,
        "severity": severity,
        "detail": detail,
    }


def _is_local(host: str) -> bool:
    from .startup_guard import is_local_bind

    return is_local_bind(host)


# Each signal is a function(state) -> signal dict.

def _sig_kill_switch(s):
    if s.kill_switch_active:
        return _sig("kill-switch", "Kill switch", "ACTIVE", -100, SEV_CRITICAL,
                    "Agent is paused; this overrides everything.")
    return _sig("kill-switch", "Kill switch", "off", 0, SEV_OK)


def _sig_llm_key(s):
    if s.llm_api_key_set:
        return _sig("llm-api-key", "LLM API key", "set", 0, SEV_OK)
    return _sig("llm-api-key", "LLM API key", "unset", -50, SEV_CRITICAL,
                "Agent cannot call the model.")


def _sig_bearer(s):
    if s.bearer_token_set:
        return _sig("bearer-token", "Bearer token", "set", 0, SEV_OK)
    return _sig("bearer-token", "Bearer token", "unset", -30, SEV_CRITICAL,
                "HTTP surface is unauthenticated.")


def _sig_approval(s):
    if s.approval_mode == "smart":
        return _sig("approval-mode", "Approval mode", "smart", 0, SEV_OK)
    if s.approval_mode == "manual":
        return _sig("approval-mode", "Approval mode", "manual", 5, SEV_OK,
                    "Every code-exec call needs confirmation.")
    return _sig("approval-mode", "Approval mode", "off", -25, SEV_WARNING,
                "Only the hardline blocklist applies.")


def _sig_dev_bind(s):
    if not s.dev_mode:
        return _sig("dev-mode-bind", "Dev mode / bind", "off", 0, SEV_OK)
    if _is_local(s.bind_host):
        return _sig("dev-mode-bind", "Dev mode / bind", "on (localhost-only)", -1, SEV_INFO)
    return _sig("dev-mode-bind", "Dev mode / bind", "DANGEROUS - public bind", -40, SEV_CRITICAL,
                f"dev_mode on with public bind {s.bind_host!r}.")


def _sig_gate_coverage(s):
    total, covered = s.gate_paths_total, s.gate_paths_covered
    if total <= 0:
        return _sig("gate-coverage", "Untrusted-content gate", "no paths declared", -5, SEV_INFO,
                    "Declare ingest paths so coverage can be measured.")
    ungated = max(0, total - covered)
    delta = -round(20 * ungated / total)
    sev = SEV_OK if ungated == 0 else (SEV_WARNING if delta <= -10 else SEV_INFO)
    return _sig("gate-coverage", "Untrusted-content gate", f"{covered}/{total} paths",
                delta, sev)


def _sig_log_redaction(s):
    if s.log_redaction_active:
        return _sig("log-redaction", "Log redaction", "active", 0, SEV_OK)
    return _sig("log-redaction", "Log redaction", "inactive", -15, SEV_WARNING,
                "Tool results may log raw secrets.")


def _sig_subprocess(s):
    if s.subprocess_envs_stripped:
        return _sig("subprocess-envs", "Subprocess envs", "all spawn sites stripped", 0, SEV_OK)
    return _sig("subprocess-envs", "Subprocess envs", "unstripped sites", -15, SEV_WARNING,
                "Subprocesses inherit secrets.")


def _sig_hardline(s):
    n = s.hardline_pattern_count
    if n > 0:
        return _sig("hardline-blocklist", "Hardline blocklist", f"{n} patterns", 0, SEV_OK)
    return _sig("hardline-blocklist", "Hardline blocklist", "missing", -20, SEV_WARNING,
                "No immutable destructive-command blocklist present.")


def _sig_csp(s):
    if s.csp_status == "enforcing":
        return _sig("csp-status", "CSP", "enforcing", 0, SEV_OK)
    if s.csp_status == "report-only":
        return _sig("csp-status", "CSP", "report-only", -10, SEV_INFO,
                    "Gathering violations; flip to enforcing when clean.")
    return _sig("csp-status", "CSP", "disabled", -20, SEV_WARNING)


def _sig_token_audit(s):
    if s.token_scope_audited:
        return _sig("token-scope-audit", "Token scope audit", "audited", 0, SEV_OK)
    return _sig("token-scope-audit", "Token scope audit", "pending", -3, SEV_INFO,
                "Confirm each token uses minimal scope.")


def _sig_db_readonly(s):
    if s.db_readonly_active:
        return _sig("db-readonly-role", "DB read-only role", "active", 0, SEV_OK)
    return _sig("db-readonly-role", "DB read-only role", "pending", -3, SEV_INFO)


def _sig_csrf(s):
    if s.csrf_origin_gate:
        return _sig("csrf-origin-gate", "CSRF/origin gate", "present", 0, SEV_OK)
    return _sig("csrf-origin-gate", "CSRF/origin gate", "absent", -10, SEV_WARNING,
                "State-changing requests are not origin-checked.")


def _sig_cve(s):
    rec = s.cve_record
    if not rec:
        return _sig("cve-scan", "CVE scan", "never run", -5, SEV_INFO)
    if rec.get("error_message"):
        return _sig("cve-scan", "CVE scan", "scanner error", -10, SEV_WARNING,
                    str(rec.get("error_message"))[:200])
    generated = rec.get("generated_at")
    if isinstance(generated, (int, float)):
        age_days = (s.now() - generated) / 86400
        if age_days > 14:
            return _sig("cve-scan", "CVE scan", f"stale ({int(age_days)}d)", -5, SEV_INFO)
    count = int(rec.get("cve_count", 0) or 0)
    if count == 0:
        return _sig("cve-scan", "CVE scan", "clean", 0, SEV_OK)
    delta = max(-25, -5 * count)  # -5 per package, capped at -25
    return _sig("cve-scan", "CVE scan", f"{count} CVEs", delta, SEV_WARNING)


_SIGNALS: List[Callable[[SecurityState], dict]] = [
    _sig_kill_switch,
    _sig_llm_key,
    _sig_bearer,
    _sig_approval,
    _sig_dev_bind,
    _sig_gate_coverage,
    _sig_log_redaction,
    _sig_subprocess,
    _sig_hardline,
    _sig_csp,
    _sig_token_audit,
    _sig_db_readonly,
    _sig_csrf,
    _sig_cve,
]


def score_color(score: int) -> str:
    if score >= 85:
        return "green"
    if score >= 60:
        return "amber"
    return "red"


def compute_audit(state: SecurityState) -> Dict[str, object]:
    """Run all signals; return ``{score, color, signals}``."""
    signals = [fn(state) for fn in _SIGNALS]
    raw = 100 + sum(int(s["delta"]) for s in signals)
    score = max(0, min(100, raw))
    return {
        "score": score,
        "color": score_color(score),
        "signals": signals,
        "generated_at": state.now(),
    }
