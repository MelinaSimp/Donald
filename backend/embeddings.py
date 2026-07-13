"""Embeddings — turning text into vectors for semantic recall (M2).

The store is written against a small ``Embedder`` protocol so the model is
swappable. Ship with a dependency-free, deterministic ``HashingEmbedder`` so
dev and tests need no API key or network; swap in a real provider (Voyage,
OpenAI, a local model) in production by implementing the same ``embed`` method.

The hashing embedder is a normalized bag-of-hashed-tokens vector: texts that
share words land near each other under cosine similarity. It is not as good as a
learned model, but it makes retrieval real and testable end to end today.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Any, Protocol, Sequence, runtime_checkable

_WORD = re.compile(r"[a-z0-9']+")


@runtime_checkable
class Embedder(Protocol):
    dim: int

    def embed(self, text: str) -> list[float]: ...


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity. Inputs are assumed non-empty and equal length."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class HashingEmbedder:
    """Deterministic, offline embedder. No dependencies, no network.

    Each token is hashed to a bucket; a second hash gives a sign, so unrelated
    tokens can cancel rather than only add. The vector is L2-normalized, so
    cosine similarity is just the dot product.
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _tokens(self, text: str) -> list[str]:
        return _WORD.findall(text.lower())

    def embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for tok in self._tokens(text):
            h = hashlib.sha1(tok.encode()).digest()
            bucket = int.from_bytes(h[:4], "big") % self.dim
            sign = 1.0 if h[4] & 1 else -1.0
            vec[bucket] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0.0:
            vec = [v / norm for v in vec]
        return vec

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


class RemoteEmbedder:
    """A learned embedder behind an OpenAI-compatible ``/embeddings`` endpoint.

    Works with OpenAI, Voyage's OpenAI-compatible route, or a local server —
    anything that accepts ``{"model", "input"}`` and returns
    ``{"data": [{"embedding": [...]}]}``. The HTTP client is injectable so tests
    never touch the network.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        model: str = "text-embedding-3-small",
        dim: int = 1536,
        http: Any | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.dim = dim
        self._http = http  # inject a fake in tests; else lazily create httpx

    def _client(self):
        if self._http is None:
            import httpx

            self._http = httpx.Client(timeout=30.0)
        return self._http

    def _post(self, inputs: list[str]) -> list[list[float]]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        resp = self._client().post(
            f"{self.base_url}/embeddings",
            headers=headers,
            json={"model": self.model, "input": inputs},
        )
        if getattr(resp, "status_code", 200) >= 400:
            raise RuntimeError(f"embeddings endpoint returned {resp.status_code}")
        data = resp.json()["data"]
        return [row["embedding"] for row in data]

    def embed(self, text: str) -> list[float]:
        return self._post([text])[0]

    def embed_batch(self, texts: Sequence[str]) -> list[list[float]]:
        return self._post(list(texts))


def get_embedder() -> Embedder:
    """Pick the embedder from the environment.

    ``EMBEDDINGS_PROVIDER=remote`` uses ``RemoteEmbedder`` (needs
    ``EMBEDDINGS_BASE_URL``; optional ``EMBEDDINGS_API_KEY`` / ``_MODEL`` /
    ``_DIM``). Anything else (the default) uses the offline ``HashingEmbedder``.

    Embeddings are tied to the embedder that wrote them — switching providers
    means re-embedding existing memory. The store guards against mixing by
    skipping vectors whose dimension differs from the current query.
    """
    if os.getenv("EMBEDDINGS_PROVIDER", "hashing").lower() == "remote":
        base = os.getenv("EMBEDDINGS_BASE_URL")
        if not base:
            raise RuntimeError("EMBEDDINGS_PROVIDER=remote needs EMBEDDINGS_BASE_URL")
        return RemoteEmbedder(
            base_url=base,
            api_key=os.getenv("EMBEDDINGS_API_KEY"),
            model=os.getenv("EMBEDDINGS_MODEL", "text-embedding-3-small"),
            dim=int(os.getenv("EMBEDDINGS_DIM", "1536")),
        )
    return HashingEmbedder(dim=int(os.getenv("EMBEDDINGS_DIM", "256")))
