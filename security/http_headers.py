"""2.2 - Strict security headers + CSP.

Threat T4 (public-surface attack): MIME sniffing, clickjacking, referrer
leakage, and XSS via inline-script-heavy admin UIs. ``security_headers()``
returns the header dict to apply to every response.

CSP ships in REPORT-ONLY mode by default. Wire a ``POST
/api/security/csp-report`` endpoint that logs violations, run a full session
through every code path (login, voice loop, web fetches, uploads), then widen
the policy by what *actually* got blocked -- not by what you guessed. Once a
full session reports zero violations, flip ``report_only=False`` to enforce.

    from security.http_headers import security_headers
    for k, v in security_headers(report_only=True).items():
        response.headers[k] = v

Note: ``'unsafe-inline'`` is retained for script/style because most
single-file UI shells carry inline JS+CSS. Moving to nonced inline is a
larger refactor -- a documented known gap. ``'unsafe-eval'`` is NEVER added;
it defeats most of CSP.
"""

from __future__ import annotations

from typing import Dict, List, Optional

# The five static headers, independent of CSP.
STATIC_HEADERS: Dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "X-Frame-Options": "DENY",
    # autoplay is listed explicitly so the policy does not silently block a
    # TTS / voice-playback path.
    "Permissions-Policy": (
        "microphone=(self), autoplay=(self), camera=(), "
        "geolocation=(), interest-cohort=()"
    ),
}

# Starting CSP -- refine against real report-only data before enforcing.
# Values are lists of source expressions; callers extend with their CDNs,
# font origins, external image/API hosts.
DEFAULT_CSP_DIRECTIVES: Dict[str, List[str]] = {
    "default-src": ["'self'"],
    "script-src": ["'self'", "'unsafe-inline'"],
    "style-src": ["'self'", "'unsafe-inline'"],
    "font-src": ["'self'", "data:"],
    "img-src": ["'self'", "data:", "blob:"],
    "media-src": ["'self'", "blob:"],
    "connect-src": ["'self'", "ws:", "wss:"],
    "frame-ancestors": ["'none'"],
    "base-uri": ["'self'"],
    "form-action": ["'self'"],
    "object-src": ["'none'"],
}

_FORBIDDEN_CSP_SOURCES = {"'unsafe-eval'"}


def build_csp(
    directives: Optional[Dict[str, List[str]]] = None,
    report_uri: Optional[str] = "/api/security/csp-report",
    report_to: Optional[str] = "csp-endpoint",
) -> str:
    """Serialize a CSP directive map to a header value.

    Refuses ``'unsafe-eval'`` anywhere -- it defeats most of CSP and is almost
    never needed.
    """
    directives = directives or DEFAULT_CSP_DIRECTIVES
    parts: List[str] = []
    for name, sources in directives.items():
        for src in sources:
            if src in _FORBIDDEN_CSP_SOURCES:
                raise ValueError(
                    f"Refusing to build a CSP containing {src}; it defeats most "
                    "of CSP's protection and is almost never required."
                )
        parts.append(f"{name} {' '.join(sources)}".strip())
    if report_uri:
        parts.append(f"report-uri {report_uri}")
    if report_to:
        parts.append(f"report-to {report_to}")
    return "; ".join(parts)


def security_headers(
    report_only: bool = True,
    csp_directives: Optional[Dict[str, List[str]]] = None,
    report_uri: str = "/api/security/csp-report",
    report_to: str = "csp-endpoint",
) -> Dict[str, str]:
    """Return the full header dict (static headers + CSP + reporting wiring).

    ``report_only=True`` (default) sends ``Content-Security-Policy-Report-Only``
    so you gather real violation data without breaking the page. Flip to
    ``False`` only after a clean report-only session to enforce.
    """
    headers = dict(STATIC_HEADERS)
    csp_value = build_csp(csp_directives, report_uri=report_uri, report_to=report_to)
    header_name = (
        "Content-Security-Policy-Report-Only" if report_only else "Content-Security-Policy"
    )
    headers[header_name] = csp_value
    # Modern reporting wiring (report-to / Reporting-Endpoints) alongside the
    # legacy report-uri carried in the CSP string above.
    headers["Reporting-Endpoints"] = f'{report_to}="{report_uri}"'
    return headers


def csp_status(report_only: bool, enabled: bool = True) -> str:
    """Map config to the audit-shield ``csp-status`` value."""
    if not enabled:
        return "disabled"
    return "report-only" if report_only else "enforcing"
