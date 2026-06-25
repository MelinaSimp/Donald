"""1.1 - Log redaction.

Threat T1 (account/key compromise): API keys, tokens, and PII leak through
stack traces, journals, and console output when a tool router logs raw API
responses verbatim. ``redact()`` masks the high-precision shapes before the
text ever reaches a log sink.

Usage::

    from security.log_redact import redact
    log.info("Tool %s result: %s", name, redact(result))

``max_len`` is deliberately separate from the regex pass so callers can dial
verbosity without changing what gets masked. Redaction runs first, then the
result is truncated -- so a secret can never survive by sitting past the
truncation boundary.
"""

from __future__ import annotations

import re
from typing import Callable, List, Tuple

# Hard cap on how much text we run the regex pass over. Protects against a
# pathological multi-megabyte tool result turning logging into a CPU sink.
_SCAN_CAP = 200_000


def _mask_keep_prefix(prefix_len: int) -> Callable[[re.Match], str]:
    def repl(m: re.Match) -> str:
        s = m.group(0)
        return s[:prefix_len] + "<redacted>"

    return repl


def _mask_email(m: re.Match) -> str:
    local, domain = m.group(1), m.group(2)
    head = local[0] if local else "*"
    return f"{head}***@{domain}"


def _mask_cc(m: re.Match) -> str:
    digits = re.sub(r"\D", "", m.group(0))
    if len(digits) < 13:
        return m.group(0)
    return "**** **** **** " + digits[-4:]


# Order matters: more specific / structural shapes first so a later, broader
# rule does not partially rewrite an already-masked span.
#
# Each entry is (compiled_regex, replacement). Replacement is either a string
# (supporting backrefs) or a callable taking the match.
_REDACTORS: List[Tuple[re.Pattern, object]] = [
    # Authorization: Bearer <token>  ->  Authorization: <redacted>
    (re.compile(r"(?i)\bauthorization\s*:\s*bearer\s+\S+"), "Authorization: <redacted>"),
    # Generic "bearer <token>" appearing inline.
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-]{12,}"), "Bearer <redacted>"),
    # Connection-string passwords: scheme://user:pass@host -> scheme://user:<pass>@host
    (
        re.compile(r"(?i)\b([a-z][a-z0-9+.\-]*://[^:/?#\s]+):([^@/?#\s]+)@"),
        r"\1:<pass>@",
    ),
    # --- Provider API key shapes (mask, keeping a short prefix for triage) ---
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{8,}"), _mask_keep_prefix(7)),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}"), _mask_keep_prefix(3)),
    (re.compile(r"\b[sprk]k_(?:live|test)_[A-Za-z0-9]{8,}"), _mask_keep_prefix(8)),
    (re.compile(r"\bgh[posru]_[A-Za-z0-9]{20,}"), _mask_keep_prefix(4)),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), _mask_keep_prefix(11)),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"), _mask_keep_prefix(5)),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), _mask_keep_prefix(4)),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b"), _mask_keep_prefix(4)),
    (re.compile(r"\bdop_v1_[A-Za-z0-9]{16,}"), _mask_keep_prefix(7)),
    (re.compile(r"\bhvs\.[A-Za-z0-9_\-]{16,}"), _mask_keep_prefix(4)),
    # JWT: three base64url segments separated by dots.
    (
        re.compile(r"\beyJ[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}\.[A-Za-z0-9_\-]{6,}"),
        "<jwt:redacted>",
    ),
    # Credit-card-shaped numbers, keep last 4.
    (
        re.compile(r"\b(?:\d[ \-]?){13,19}\b"),
        _mask_cc,
    ),
    # Email addresses: mask local part, keep domain.
    (
        re.compile(r"\b([A-Za-z0-9._%+\-]+)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b"),
        _mask_email,
    ),
]


def redact(text: object, max_len: int = 500) -> str:
    """Mask secret/PII shapes in ``text`` then truncate to ``max_len``.

    Accepts any object (coerced via ``str``) so it is safe to wrap around a
    raw tool result of unknown type. ``max_len <= 0`` disables truncation.
    """
    if not isinstance(text, str):
        text = str(text)

    scanned = text[:_SCAN_CAP]
    overflow = text[_SCAN_CAP:]
    for pattern, repl in _REDACTORS:
        scanned = pattern.sub(repl, scanned)
    result = scanned + overflow

    if max_len and max_len > 0 and len(result) > max_len:
        hidden = len(result) - max_len
        result = result[:max_len] + f"...(+{hidden} chars)"
    return result
