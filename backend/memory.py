"""The memory layer (M2) — what makes Donald feel like it remembers you.

Three tiers, all per-user and all in ``memory_items``:

* **facts**   — durable profile ("prefers concise answers", "works at X").
* **chunks**  — embedded pieces of past conversations / files / notes (RAG).
* **episodes**— short summaries written after a session.

On each turn the caller injects ``context_block(user_id, query)`` into the
system prompt: the user's profile facts plus the top-K semantically closest
chunks/episodes. That retrieve-and-inject loop is the difference between a
chatbot and something that knows you.

Isolation: every read and write is scoped to ``user_id`` — one user's memory is
never visible to another. Ranking is cosine similarity in Python over the user's
items (a bounded set); see migrations/002_memory.sql for the pgvector upgrade
path when volume grows.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from .db import DB
from .embeddings import Embedder, HashingEmbedder, cosine

FACT, CHUNK, EPISODE = "fact", "chunk", "episode"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return uuid.uuid4().hex


@dataclass
class MemoryHit:
    id: str
    kind: str
    content: str
    category: str
    source: str | None
    score: float
    created_at: str


class MemoryStore:
    def __init__(self, db: DB, embedder: Embedder | None = None) -> None:
        self.db = db
        self.embedder = embedder or HashingEmbedder()

    # ── writes ────────────────────────────────────────────────────────────
    def _add(
        self, user_id: str, kind: str, content: str,
        category: str = "general", source: str | None = None,
    ) -> str | None:
        content = content.strip()
        if not content:
            return None
        # Exact-dedup per user+kind: re-storing the same statement refreshes it
        # rather than piling up duplicates that would skew retrieval.
        existing = self.db.query_one(
            "SELECT id FROM memory_items WHERE user_id = ? AND kind = ? "
            "AND content = ?",
            (user_id, kind, content),
        )
        now = _now()
        if existing:
            self.db.execute(
                "UPDATE memory_items SET updated_at = ? WHERE id = ?",
                (now, existing["id"]),
            )
            return existing["id"]
        item_id = _uid()
        embedding = json.dumps(self.embedder.embed(content))
        self.db.execute(
            "INSERT INTO memory_items (id, user_id, kind, content, category, "
            "source, embedding, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (item_id, user_id, kind, content, category, source, embedding, now, now),
        )
        return item_id

    def add_fact(self, user_id: str, content: str, category: str = "general") -> str | None:
        return self._add(user_id, FACT, content, category=category)

    def add_chunk(self, user_id: str, content: str, source: str = "conversation") -> str | None:
        return self._add(user_id, CHUNK, content, source=source)

    def add_episode(self, user_id: str, summary: str, run_id: str | None = None) -> str | None:
        return self._add(user_id, EPISODE, summary, source=run_id)

    # ── reads ─────────────────────────────────────────────────────────────
    def facts(self, user_id: str, limit: int = 50) -> list[str]:
        rows = self.db.query(
            "SELECT content FROM memory_items WHERE user_id = ? AND kind = ? "
            "ORDER BY updated_at DESC LIMIT ?",
            (user_id, FACT, limit),
        )
        return [r["content"] for r in rows]

    def facts_full(self, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Facts with ids, so the UI can show and delete individual entries."""
        return self.db.query(
            "SELECT id, content, created_at FROM memory_items WHERE user_id = ? "
            "AND kind = ? ORDER BY updated_at DESC LIMIT ?",
            (user_id, FACT, limit),
        )

    def delete(self, user_id: str, item_id: str) -> bool:
        """Delete one memory item — scoped to the user, so no one can delete
        another user's memory even with a guessed id."""
        existing = self.db.query_one(
            "SELECT id FROM memory_items WHERE user_id = ? AND id = ?",
            (user_id, item_id),
        )
        if not existing:
            return False
        self.db.execute(
            "DELETE FROM memory_items WHERE user_id = ? AND id = ?", (user_id, item_id)
        )
        return True

    def search(
        self, user_id: str, query: str, k: int = 5, kinds: tuple[str, ...] | None = None,
    ) -> list[MemoryHit]:
        """Top-k of the user's items by cosine similarity to ``query``."""
        if kinds:
            placeholders = ",".join("?" for _ in kinds)
            rows = self.db.query(
                f"SELECT * FROM memory_items WHERE user_id = ? "
                f"AND kind IN ({placeholders})",
                (user_id, *kinds),
            )
        else:
            rows = self.db.query(
                "SELECT * FROM memory_items WHERE user_id = ?", (user_id,)
            )
        if not rows:
            return []
        q = self.embedder.embed(query)
        hits = []
        for r in rows:
            emb = json.loads(r["embedding"])
            if len(emb) != len(q):
                # Written by a different embedder (dimension mismatch): can't be
                # compared meaningfully, so skip rather than mis-rank. Re-embed
                # to bring these back into play after an embedder switch.
                continue
            hits.append(
                MemoryHit(
                    id=r["id"], kind=r["kind"], content=r["content"],
                    category=r["category"], source=r["source"],
                    score=cosine(q, emb), created_at=r["created_at"],
                )
            )
        # Rank by similarity, breaking ties toward more recent items.
        hits.sort(key=lambda h: (h.score, h.created_at), reverse=True)
        return [h for h in hits[:k] if h.score > 0.0]

    def context_block(self, user_id: str, query: str | None = None, k: int = 5) -> str:
        """A system-prompt block: profile facts + top-K relevant chunks/episodes."""
        parts: list[str] = []
        facts = self.facts(user_id)
        if facts:
            parts.append(
                "What you know about the user (from earlier sessions):\n"
                + "\n".join(f"- {f}" for f in facts)
            )
        if query:
            hits = self.search(user_id, query, k=k, kinds=(CHUNK, EPISODE))
            if hits:
                parts.append(
                    "Relevant context from past conversations:\n"
                    + "\n".join(f"- {h.content}" for h in hits)
                )
        return "\n\n".join(parts)
