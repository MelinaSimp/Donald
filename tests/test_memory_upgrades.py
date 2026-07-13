"""M2 upgrades: pluggable remote embedder and the post-session summarizer."""

from __future__ import annotations

import pytest

from backend.db import open_db
from backend.embeddings import HashingEmbedder, RemoteEmbedder
from backend.memory import MemoryStore
from backend.memory_service import MemoryService
from backend.repo import UserRepo
from backend.summarize import summarize_session


# ── remote embedder (fake HTTP) ──────────────────────────────────────────────
class _FakeResp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


class _FakeHTTP:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        return _FakeResp(self._payload)


def test_remote_embedder_calls_endpoint_and_parses():
    http = _FakeHTTP({"data": [{"embedding": [0.1, 0.2, 0.3]}]})
    emb = RemoteEmbedder(base_url="https://api.example.com/v1", api_key="k",
                         model="m", dim=3, http=http)
    assert emb.embed("hello") == [0.1, 0.2, 0.3]
    call = http.calls[0]
    assert call["url"].endswith("/embeddings")
    assert call["headers"]["Authorization"] == "Bearer k"
    assert call["json"] == {"model": "m", "input": ["hello"]}


def test_remote_embedder_http_error_raises():
    class Boom:
        def post(self, *a, **k):
            return _FakeResp({}, status=500)
    with pytest.raises(RuntimeError):
        RemoteEmbedder(base_url="x", http=Boom()).embed("hi")


def test_store_skips_mismatched_dim_vectors():
    # A vector written by a different-dim embedder must not crash or mis-rank.
    db = open_db("sqlite://:memory:")
    uid = UserRepo(db).create("dim@example.com", "longenough1").id
    MemoryStore(db, HashingEmbedder(dim=64)).add_chunk(uid, "written with dim 64")
    # Query with a different-dim embedder: the old vector is skipped, no crash.
    results = MemoryStore(db, HashingEmbedder(dim=256)).search(uid, "written")
    assert results == []


# ── summarizer ───────────────────────────────────────────────────────────────
TRANSCRIPT = [
    {"role": "user", "content": "I'm Ada and I prefer terse answers."},
    {"role": "assistant", "content": "Got it, Ada."},
    {"role": "user", "content": "Help me plan the Q3 launch."},
]


def test_summarizer_model_mode_parses_json():
    def fake_llm(prompt):
        assert "Q3 launch" in prompt  # transcript was rendered into the prompt
        return '{"facts": ["Name is Ada", "Prefers terse answers"], ' \
               '"summary": "Planned the Q3 launch."}'
    facts, summary = summarize_session(TRANSCRIPT, llm=fake_llm)
    assert "Name is Ada" in facts and summary == "Planned the Q3 launch."


def test_summarizer_tolerates_chatty_model():
    def chatty(prompt):
        return 'Sure! Here you go:\n{"facts": [], "summary": "A short chat."}\nHope that helps!'
    facts, summary = summarize_session(TRANSCRIPT, llm=chatty)
    assert facts == [] and summary == "A short chat."


def test_summarizer_falls_back_when_model_breaks():
    def broken(prompt):
        raise RuntimeError("model down")
    facts, summary = summarize_session(TRANSCRIPT, llm=broken)
    # Heuristic still pulls the first-person fact and a summary.
    assert any("Ada" in f for f in facts) and summary


def test_summarizer_heuristic_without_model():
    facts, summary = summarize_session(TRANSCRIPT)  # no llm
    assert any("prefer" in f.lower() for f in facts)
    assert "Q3 launch" in summary


def test_service_summarize_stores_facts_and_episode():
    db = open_db("sqlite://:memory:")
    uid = UserRepo(db).create("svc@example.com", "longenough1").id
    svc = MemoryService(db)

    def fake_llm(prompt):
        return '{"facts": ["Works on a launch"], "summary": "Discussed the launch."}'

    summary = svc.summarize_session(uid, TRANSCRIPT, run_id="r1", llm=fake_llm)
    assert summary == "Discussed the launch."
    assert "Works on a launch" in svc.store.facts(uid)
    # The episode is retrievable as memory.
    hits = svc.store.search(uid, "what did we discuss about the launch?")
    assert any("launch" in h.content.lower() for h in hits)
