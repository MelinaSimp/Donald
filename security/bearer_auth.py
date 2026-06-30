"""2.1 - Bearer token verification with rotation overlap.

Threat T1 (key compromise): a static bearer token can never be rotated
without a hard cutoff that breaks every client. ``BearerVerifier`` accepts
TWO valid tokens at once -- CURRENT (primary) and PREV (the prior value,
honored during a rotation window) -- both compared in constant time.

Rotation procedure (document in your README / secrets manager):

    1. Copy CURRENT -> PREV in the secrets manager.
    2. Generate a new value; set it as CURRENT.
    3. Redeploy.
    4. After all clients re-pair (~1h solo, ~24h team), unset PREV.

During the overlap both authenticate; after PREV is cleared, only the new
one works. Clients never hit a hard cutoff.
"""

from __future__ import annotations

import hmac
from typing import Optional

_BEARER_PREFIX = "bearer "


def extract_bearer(authorization_header: Optional[str]) -> Optional[str]:
    """Pull the raw token out of an ``Authorization: Bearer <token>`` header."""
    if not authorization_header:
        return None
    header = authorization_header.strip()
    if header[: len(_BEARER_PREFIX)].lower() != _BEARER_PREFIX:
        return None
    token = header[len(_BEARER_PREFIX) :].strip()
    return token or None


def _ct_equal(a: Optional[str], b: Optional[str]) -> bool:
    """Constant-time string equality that tolerates None/empty configs."""
    if not a or not b:
        return False
    return hmac.compare_digest(a, b)


class BearerVerifier:
    """Verify a presented bearer token against CURRENT and optional PREV.

    Both comparisons run on every call (no short-circuit) so a caller cannot
    learn *which* token matched from response timing. ``verify()`` returns the
    matching slot name (``"current"`` / ``"previous"``) or ``None``.
    """

    def __init__(self, current: str, previous: Optional[str] = None) -> None:
        if not current:
            raise ValueError("BearerVerifier requires a non-empty CURRENT token.")
        self._current = current
        self._previous = previous or None

    def verify(self, presented: Optional[str]) -> Optional[str]:
        matched_current = _ct_equal(presented, self._current)
        matched_previous = _ct_equal(presented, self._previous)
        if matched_current:
            return "current"
        if matched_previous:
            return "previous"
        return None

    def is_valid(self, presented: Optional[str]) -> bool:
        return self.verify(presented) is not None

    def verify_header(self, authorization_header: Optional[str]) -> Optional[str]:
        """Convenience: extract from a raw header then verify."""
        return self.verify(extract_bearer(authorization_header))
