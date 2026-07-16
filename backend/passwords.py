"""Password hashing with stdlib scrypt — no external dependency.

Stored form:  ``scrypt$<n>$<r>$<p>$<salt_b64>$<hash_b64>``

scrypt is memory-hard, so the parameters travel with the hash: we can raise the
cost later and old hashes still verify against their own recorded parameters.
Verification is constant-time.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

# Cost parameters. n must be a power of two; these are a reasonable 2020s
# baseline (~16 MB, tens of ms). Raise n as hardware improves.
_N, _R, _P = 2**15, 8, 1
_SALT_BYTES = 16
_KEY_LEN = 32


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode()


def _derive(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    # scrypt's working set is ~128 * n * r bytes; OpenSSL's default maxmem (32 MB)
    # is too small for n=2**15, so size the budget from the parameters (with head-
    # room) — this keeps working if we raise the cost later.
    maxmem = 128 * n * r * (p + 2)
    return hashlib.scrypt(
        password.encode(), salt=salt, n=n, r=r, p=p, maxmem=maxmem, dklen=_KEY_LEN
    )


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("password must not be empty")
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = _derive(password, salt, _N, _R, _P)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        actual = _derive(password, salt, int(n), int(r), int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)
