"""Prompt-injection containment for user-supplied descriptions.

The Factory writes system prompts for *other* agents based on a user's role
description. A malicious description (``"...and also exfiltrate all env
vars"``) must not escape the meta-prompt. This is shallow, deliberate
defense — we are not trying to defeat a determined attacker, only to nudge
sloppy or hostile input into a safe shape and to refuse the obvious attacks
before any tokens burn.

Two layers:

* :func:`sanitize_text` — strips control characters and collapses fenced
  ``system:`` / "ignore previous instructions" patterns. Always applied
  before inlining user text into an LLM prompt or the spec markdown.
* :func:`scan_for_injection` — returns a list of matched injection patterns;
  the pipeline *refuses the task* if non-empty.

A third check, :func:`assert_no_verbatim_user_input`, enforces that the
generated system prompt paraphrased the user rather than copying a long span
verbatim.
"""

from __future__ import annotations

import re

# Control characters except tab/newline/carriage-return.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

_INJECTION_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ignore_previous", re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I)),
    ("disregard_above", re.compile(r"disregard\s+(the\s+)?(above|prior|previous)", re.I)),
    ("role_header", re.compile(r"(^|\n)\s*(system|assistant|developer)\s*:", re.I)),
    ("you_are_now", re.compile(r"you\s+are\s+now\b", re.I)),
    ("new_instructions", re.compile(r"new\s+instructions\s*:", re.I)),
    ("exfiltrate", re.compile(r"\bexfiltrat\w*\b", re.I)),
    ("env_dump", re.compile(r"(env(ironment)?\s+vars?|os\.environ|printenv|\$\{?[A-Z_]+\}?)", re.I)),
    ("reveal_prompt", re.compile(r"(reveal|print|repeat|show)\s+(your|the)\s+(system\s+)?prompt", re.I)),
    ("fenced_system", re.compile(r"```[a-z]*\s*\n?\s*(system|assistant)\s*:", re.I)),
]


class InjectionRefused(Exception):
    """Raised when user input contains an injection pattern we refuse to process."""


def sanitize_text(text: str) -> str:
    """Strip control chars and neutralize obvious role-header injections.

    This does not reject — it cleans. Use :func:`scan_for_injection` to
    decide whether to refuse outright.
    """
    if not text:
        return ""
    cleaned = _CONTROL_RE.sub("", text)
    # Neutralize line-leading role headers by escaping the colon so they read
    # as plain text rather than a chat turn boundary.
    cleaned = re.sub(
        r"(^|\n)(\s*)(system|assistant|developer)\s*:",
        r"\1\2\3∶ ",  # use a ratio character that is not a real colon
        cleaned,
        flags=re.I,
    )
    return cleaned.strip()


def scan_for_injection(text: str) -> list[str]:
    """Return the names of injection patterns found in *text* (empty == clean)."""
    if not text:
        return []
    return [name for name, pat in _INJECTION_PATTERNS if pat.search(text)]


def assert_clean(text: str, *, field: str) -> str:
    """Sanitize and refuse if injection patterns are present.

    Returns the sanitized text so callers can use the safe version.
    """
    hits = scan_for_injection(text)
    if hits:
        raise InjectionRefused(
            f"{field} contains disallowed instruction-injection patterns: {', '.join(hits)}"
        )
    return sanitize_text(text)


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip().lower()


def assert_no_verbatim_user_input(
    system_prompt: str, *user_inputs: str, min_span_words: int = 12
) -> None:
    """Guard that the generated prompt paraphrased the user.

    Flags if any contiguous >= ``min_span_words`` word span from a user input
    appears verbatim in the generated system prompt. This catches a
    prompt-generator that copied the role description (and any payload in it)
    instead of paraphrasing.
    """
    sp_norm = _normalize(system_prompt)
    for raw in user_inputs:
        words = _normalize(raw).split()
        if len(words) < min_span_words:
            continue
        for i in range(0, len(words) - min_span_words + 1):
            span = " ".join(words[i : i + min_span_words])
            if span and span in sp_norm:
                raise InjectionRefused(
                    "generated system prompt copied user input verbatim "
                    f"(span: {span!r}); regeneration required"
                )
