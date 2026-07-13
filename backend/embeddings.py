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
import re
from typing import Protocol, Sequence, runtime_checkable

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
