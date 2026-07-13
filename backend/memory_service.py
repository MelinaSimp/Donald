"""MemoryService — the memory API the gateway uses per turn.

Two jobs:

* ``context_block(user_id, message)`` — what to inject into the system prompt
  before the model runs (profile facts + retrieved chunks).
* ``remember(user_id, user_msg, assistant_msg, run_id)`` — what to persist after
  the turn: the exchange as a retrievable chunk, plus any durable facts.

Fact extraction here is a deliberately simple offline heuristic (first-person
statements). The production upgrade is a cheap-model extractor + episodic
summarizer running off a queue — same ``MemoryStore`` underneath; only this
class changes. Kept model-free so it runs and tests without an API key.
"""

from __future__ import annotations

import re

from .db import DB
from .embeddings import Embedder
from .memory import MemoryStore

# First-person cues that usually introduce a durable fact worth keeping.
_FACT_CUES = re.compile(
    r"^\s*(?:remember that |remember |note that |for the record[,:]? )?"
    r"(i am |i'm |my |i prefer |i like |i love |i hate |i work |i live |i use |call me )",
    re.IGNORECASE,
)


class MemoryService:
    def __init__(self, db: DB, embedder: Embedder | None = None) -> None:
        self.store = MemoryStore(db, embedder)

    def context_block(self, user_id: str, message: str) -> str:
        return self.store.context_block(user_id, query=message)

    def remember(
        self, user_id: str, user_msg: str, assistant_msg: str, run_id: str | None = None
    ) -> None:
        user_msg = (user_msg or "").strip()
        if not user_msg:
            return
        # The user's message is the retrievable signal; store it as a chunk.
        self.store.add_chunk(
            user_id, f"User said: {user_msg}", source=run_id or "conversation"
        )
        fact = self._extract_fact(user_msg)
        if fact:
            self.store.add_fact(user_id, fact)

    @staticmethod
    def _extract_fact(text: str) -> str | None:
        """Turn a first-person statement into a durable third-person-ish fact."""
        if not _FACT_CUES.search(text):
            return None
        # Trim a leading "remember (that)" preamble; keep the statement itself.
        cleaned = re.sub(
            r"^\s*(?:remember that |remember |note that |for the record[,:]? )",
            "",
            text,
            flags=re.IGNORECASE,
        ).strip()
        # One sentence is plenty for a fact.
        cleaned = re.split(r"[.!?\n]", cleaned, maxsplit=1)[0].strip()
        return cleaned[:200] or None
