"""M2 semantic memory: persistence across sessions, similarity recall,
per-user isolation, and dedup. Runs on the in-memory SQLite the other backend
tests use; the same code path is exercised against Postgres in CI/deploy.
"""

from __future__ import annotations

from backend.db import open_db
from backend.embeddings import HashingEmbedder, cosine
from backend.memory import MemoryStore
from backend.repo import UserRepo


def _user(db, email="mem@example.com"):
    return UserRepo(db).create(email, "longenough1").id


# ── embedder sanity ──────────────────────────────────────────────────────────
def test_embedder_groups_related_text():
    e = HashingEmbedder()
    sail = e.embed("I love sailing on the ocean")
    boat = e.embed("sailing boats on the sea are wonderful")
    tax = e.embed("quarterly tax filing deadlines")
    # Shared vocabulary ("sailing") should pull the two boating texts closer
    # than an unrelated one.
    assert cosine(sail, boat) > cosine(sail, tax)


# ── persistence + retrieval ──────────────────────────────────────────────────
def test_facts_and_chunks_survive_a_new_store():
    db = open_db("sqlite://:memory:")
    uid = _user(db)
    MemoryStore(db).add_fact(uid, "The user is vegetarian")
    MemoryStore(db).add_chunk(uid, "We discussed a trip to Lisbon in spring")

    # A fresh store (simulating a new session/process) still recalls them.
    fresh = MemoryStore(db)
    assert "The user is vegetarian" in fresh.facts(uid)
    hits = fresh.search(uid, "where were we thinking of travelling?")
    assert any("Lisbon" in h.content for h in hits)


def test_search_ranks_relevant_first():
    # The offline embedder is lexical: a distinctive shared term ("Python")
    # surfaces the right item above others that share only stop-ish words.
    db = open_db("sqlite://:memory:")
    uid = _user(db)
    store = MemoryStore(db)
    store.add_chunk(uid, "The user's dog is named Biscuit")
    store.add_chunk(uid, "The user prefers Python over JavaScript")
    store.add_chunk(uid, "The user's flight to Berlin is on Friday")

    top = store.search(uid, "tell me about the user's Python preference", k=1)
    assert top and "Python" in top[0].content


def test_context_block_includes_profile_and_relevant():
    db = open_db("sqlite://:memory:")
    uid = _user(db)
    store = MemoryStore(db)
    store.add_fact(uid, "Prefers concise answers")
    store.add_chunk(uid, "The user is building a CRM for dentists")

    block = store.context_block(uid, query="how's my dentist CRM project going?")
    assert "Prefers concise answers" in block
    assert "dentists" in block


# ── dedup ────────────────────────────────────────────────────────────────────
def test_exact_dedup_refreshes_not_duplicates():
    db = open_db("sqlite://:memory:")
    uid = _user(db)
    store = MemoryStore(db)
    a = store.add_fact(uid, "Timezone is CET")
    b = store.add_fact(uid, "Timezone is CET")
    assert a == b  # same row refreshed
    assert store.facts(uid).count("Timezone is CET") == 1


# ── isolation (the M2 exit gate) ─────────────────────────────────────────────
def test_memory_is_per_user():
    db = open_db("sqlite://:memory:")
    alice = _user(db, "alice-mem@example.com")
    bob = _user(db, "bob-mem@example.com")
    store = MemoryStore(db)
    store.add_fact(alice, "Alice's secret project is codenamed Falcon")

    assert store.facts(bob) == []
    assert store.search(bob, "Falcon project") == []
    assert store.context_block(bob, query="Falcon") == ""
    # Alice still sees her own.
    assert "Falcon" in store.context_block(alice, query="Falcon")
