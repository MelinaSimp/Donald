"""At-rest encryption for integration tokens.

Per-user OAuth/API secrets are encrypted with Fernet (AES-128-CBC + HMAC)
before they ever touch the database, so a DB leak yields ciphertext, not
credentials. The key comes from ``BACKEND_SECRET_KEY`` (a urlsafe-base64 Fernet
key). In dev, if it's unset we mint an ephemeral key and warn — data written
under an ephemeral key won't decrypt after a restart, which is exactly what you
want to notice before shipping.

Generate a real key once and put it in your secrets manager:

    python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

log = logging.getLogger("donald.backend.crypto")


class TokenCipher:
    def __init__(self, key: str | bytes | None = None) -> None:
        key = key or os.getenv("BACKEND_SECRET_KEY")
        if not key:
            key = Fernet.generate_key()
            log.warning(
                "BACKEND_SECRET_KEY is unset — using an EPHEMERAL key. Stored "
                "integration tokens will not survive a restart. Set a real key "
                "before production."
            )
        if isinstance(key, str):
            key = key.encode()
        self._fernet = Fernet(key)

    def encrypt(self, payload: dict[str, Any]) -> str:
        raw = json.dumps(payload, separators=(",", ":")).encode()
        return self._fernet.encrypt(raw).decode()

    def decrypt(self, ciphertext: str) -> dict[str, Any]:
        try:
            raw = self._fernet.decrypt(ciphertext.encode())
        except InvalidToken as exc:  # wrong key or tampered data
            raise ValueError("could not decrypt token (wrong key or corrupt)") from exc
        return json.loads(raw)
