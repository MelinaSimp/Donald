"""1.4 - Auth rate-limit + lockout.

Threat T4 (public-surface attack): without a per-IP cap an attacker can
brute-force the bearer token against the HTTP endpoint or the WebSocket
upgrade handler. ``AuthRateLimiter`` is an in-process sliding window: after
N failed auth attempts within W seconds, the IP is locked out for L seconds.

Framework-agnostic. In your auth middleware:

    limiter = AuthRateLimiter()           # N=10, W=300, L=900

    ip = client_ip(request.headers, request.client.host)
    allowed, retry_after = limiter.check(ip)
    if not allowed:
        return Response(status_code=429, headers={"Retry-After": str(int(retry_after))})
    if not token_ok:
        limiter.record_fail(ip)
        return Response(status_code=401)
    # success: do NOT touch the limiter

Apply the SAME limiter to the WebSocket upgrade path -- that is the surface
attackers hammer if only HTTP is protected.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, Optional, Tuple

# Header order to consult when behind a reverse proxy. First non-empty wins.
# CF-Connecting-IP is a single trusted value from Cloudflare; X-Forwarded-For
# may be a list, so we take its first (left-most original client) hop.
_PROXY_IP_HEADERS = ("cf-connecting-ip", "x-real-ip", "x-forwarded-for")


def client_ip(headers: Optional[Dict[str, str]], fallback: str) -> str:
    """Resolve the real caller IP, preferring trusted proxy headers.

    ``headers`` is any case-insensitive-ish mapping (a dict of the request
    headers). ``fallback`` is the direct socket peer (``request.client.host``).
    Only use this if you actually sit behind a proxy you trust to set these;
    otherwise these headers are attacker-spoofable -- pass ``fallback`` alone.
    """
    if headers:
        lowered = {str(k).lower(): v for k, v in headers.items()}
        for name in _PROXY_IP_HEADERS:
            val = lowered.get(name)
            if val:
                # X-Forwarded-For: "client, proxy1, proxy2" -> client
                return val.split(",")[0].strip()
    return fallback


class AuthRateLimiter:
    """Per-IP sliding-window failed-auth limiter with lockout.

    Thread-safe (a single lock guards the maps). State lives in process
    memory, so each worker keeps its own counters -- fine for the
    single-process / few-worker deployments these agents typically run; for a
    fleet, back it with a shared store using the same check/record contract.
    """

    def __init__(
        self,
        max_fails: int = 10,
        window_seconds: float = 300.0,
        lockout_seconds: float = 900.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_fails = max_fails
        self.window_seconds = window_seconds
        self.lockout_seconds = lockout_seconds
        self._clock = clock
        self._fails: Dict[str, Deque[float]] = defaultdict(deque)
        self._locked_until: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _trim(self, dq: Deque[float], now: float) -> None:
        cutoff = now - self.window_seconds
        while dq and dq[0] < cutoff:
            dq.popleft()

    def check(self, ip: str) -> Tuple[bool, float]:
        """Return ``(allowed, retry_after_seconds)``. Check this FIRST.

        ``retry_after_seconds`` is the remaining lockout time when blocked,
        else ``0.0``. This call never mutates fail counters.
        """
        now = self._clock()
        with self._lock:
            until = self._locked_until.get(ip)
            if until is not None:
                if now < until:
                    return False, until - now
                # Lockout expired -- clear it.
                del self._locked_until[ip]
                self._fails.pop(ip, None)
            return True, 0.0

    def record_fail(self, ip: str) -> float:
        """Record one failed auth for ``ip``; return retry_after if it locked.

        Returns ``0.0`` if the IP is not (yet) locked out, otherwise the
        lockout duration. Crossing ``max_fails`` within the window starts the
        lockout and clears the window so a locked IP is not re-locked on every
        subsequent attempt.
        """
        now = self._clock()
        with self._lock:
            # Already locked? Keep it locked; don't extend on each try.
            until = self._locked_until.get(ip)
            if until is not None and now < until:
                return until - now

            dq = self._fails[ip]
            self._trim(dq, now)
            dq.append(now)
            if len(dq) >= self.max_fails:
                self._locked_until[ip] = now + self.lockout_seconds
                dq.clear()
                return self.lockout_seconds
            return 0.0

    def record_success(self, ip: str) -> None:
        """Clear any accumulated failures for ``ip`` after a good auth."""
        with self._lock:
            self._fails.pop(ip, None)
            self._locked_until.pop(ip, None)

    def reset(self) -> None:
        """Drop all state (mainly for tests)."""
        with self._lock:
            self._fails.clear()
            self._locked_until.clear()
