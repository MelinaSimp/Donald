"""Structural tests on the segment protocol.

These run fully offline — no API key, no network — because the segment logic
takes injected sentence streams and a fake `send_json`.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server.segment_stream import iter_sentences, stream_with_segments  # noqa: E402


async def _aiter(items):
    for it in items:
        yield it


async def _run(sentences, *, voice=True, auto_continue=False):
    """Drive stream_with_segments and return (events, recorded, full_text)."""
    events = []
    recorded = {}

    async def send_json(ev):
        events.append(ev)

    def record(seg_id, text):
        recorded[seg_id] = text

    seq = {"n": 0}

    def make_id():
        return "TURN"

    def clock():
        seq["n"] += 1
        return float(seq["n"])

    full = await stream_with_segments(
        sentences=_aiter(sentences),
        send_json=send_json,
        record_segment=record,
        voice=voice,
        auto_continue=auto_continue,
        clock=clock,
        make_id=make_id,
    )
    segs = [e for e in events if e["type"] == "speak_segment"]
    return segs, recorded, full


@pytest.mark.asyncio
async def test_single_sentence_one_final_segment():
    segs, recorded, _ = await _run(["Hello there."])
    assert len(segs) == 1
    assert segs[0]["is_final"] is True
    assert segs[0]["seq"] == 0
    assert recorded[segs[0]["turn_id"]] == "Hello there."


@pytest.mark.asyncio
async def test_multi_sentence_segment_shape():
    segs, _, _ = await _run(["One.", "Two.", "Three."])
    assert len(segs) == 3
    assert [s["seq"] for s in segs] == [0, 1, 2]
    # is_final only on the last.
    assert [s["is_final"] for s in segs] == [False, False, True]
    # All share one base_turn_id.
    assert len({s["base_turn_id"] for s in segs}) == 1


@pytest.mark.asyncio
async def test_auto_continue_rides_only_on_final():
    segs, _, _ = await _run(["A.", "B.", "C."], auto_continue=True)
    assert [s["auto_continue"] for s in segs] == [False, False, True]


@pytest.mark.asyncio
async def test_text_mode_emits_no_speak_segments():
    segs, recorded, full = await _run(["One.", "Two."], voice=False)
    assert segs == []
    assert recorded == {}
    assert full == "One. Two."


@pytest.mark.asyncio
async def test_full_text_is_concatenation():
    _, _, full = await _run(["First.", "Second."])
    assert full == "First. Second."


# --- sentence splitter -----------------------------------------------------


async def _split(deltas):
    out = []
    async for s in iter_sentences(_aiter(deltas)):
        out.append(s)
    return out


@pytest.mark.asyncio
async def test_splitter_basic_boundaries():
    out = await _split(["Hello world. ", "How are you? ", "Great!"])
    assert out == ["Hello world.", "How are you?", "Great!"]


@pytest.mark.asyncio
async def test_splitter_token_by_token():
    out = await _split(list("One. Two. Three."))
    assert out == ["One.", "Two.", "Three."]


@pytest.mark.asyncio
async def test_splitter_handles_abbreviations_and_decimals():
    out = await _split(["Dr. Smith paid 3.14 dollars to Mr. Lee. Done."])
    assert out == ["Dr. Smith paid 3.14 dollars to Mr. Lee.", "Done."]


@pytest.mark.asyncio
async def test_splitter_flushes_tail_without_punctuation():
    out = await _split(["No terminal punctuation here"])
    assert out == ["No terminal punctuation here"]
