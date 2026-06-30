"""Per-sentence segment streaming with the hold-one-ahead pattern.

This module is the heart of the latency fix. It consumes an async stream of
*sentences* produced by the LLM and emits one ``speak_segment`` event per
sentence as soon as it is ready — instead of waiting for the whole LLM
response and then requesting TTS once (the classic "Bottleneck A" dead-air
gap).

It has no FastAPI / Anthropic imports on purpose: everything external is
injected (``send_json``, ``record_segment``, ``clock``, ``make_id``) so the
logic is trivially unit-testable offline.
"""

from __future__ import annotations

import re
import time
import uuid
from typing import AsyncIterator, Awaitable, Callable

# ---------------------------------------------------------------------------
# Sentence splitting
# ---------------------------------------------------------------------------

# Tokens that end with "." but should NOT trigger a sentence break.
_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "e.g", "i.e", "a.m", "p.m", "u.s", "u.k", "no", "fig", "approx",
}

# A sentence ends on . ? or ! followed by whitespace (or end of buffer).
_SENTENCE_END = re.compile(r"([.?!]+)(\s+|$)")


def _is_false_boundary(buffer: str, end_idx: int) -> bool:
    """Return True if the punctuation at ``end_idx`` is not a real sentence end.

    Handles three common cases that would otherwise over-split:
      * known abbreviations  ("Mr." , "e.g.")
      * single-letter initials ("J. R. R. Tolkien")
      * decimals             ("3.14", "v2.0")
    """
    # Decimal: digit immediately before AND after the dot.
    if (
        end_idx > 0
        and buffer[end_idx - 1].isdigit()
        and end_idx + 1 < len(buffer)
        and buffer[end_idx + 1].isdigit()
    ):
        return True

    # Walk back to grab the word preceding the punctuation.
    j = end_idx - 1
    while j >= 0 and (buffer[j].isalnum() or buffer[j] == "."):
        j -= 1
    word = buffer[j + 1 : end_idx].lower().rstrip(".")

    if word in _ABBREVIATIONS:
        return True
    # Single-letter initial, e.g. the "J" in "J. R. R."
    if len(word) == 1 and word.isalpha():
        return True
    return False


async def iter_sentences(text_deltas: AsyncIterator[str]) -> AsyncIterator[str]:
    """Re-chunk a stream of token/text deltas into complete sentences.

    Buffers characters until a real sentence boundary is found, then yields the
    sentence (including its terminal punctuation). Whatever is left when the
    upstream finishes is flushed as a final sentence.
    """
    buffer = ""
    async for delta in text_deltas:
        if not delta:
            continue
        buffer += delta
        # Emit every complete sentence currently in the buffer.
        while True:
            match = None
            for m in _SENTENCE_END.finditer(buffer):
                if not _is_false_boundary(buffer, m.start(1)):
                    match = m
                    break
            if match is None:
                break
            cut = match.end(1)  # include the punctuation, drop trailing space
            sentence = buffer[:cut].strip()
            buffer = buffer[match.end() :]
            if sentence:
                yield sentence

    tail = buffer.strip()
    if tail:
        yield tail


# ---------------------------------------------------------------------------
# Segment emission (hold-one-ahead)
# ---------------------------------------------------------------------------


async def stream_with_segments(
    *,
    sentences: AsyncIterator[str],
    send_json: Callable[[dict], Awaitable[None]],
    record_segment: Callable[[str, str], None],
    voice: bool = True,
    auto_continue: bool = False,
    clock: Callable[[], float] = time.monotonic,
    make_id: Callable[[], str] = lambda: uuid.uuid4().hex,
    log: Callable[[str], None] | None = None,
) -> str:
    """Consume sentences and emit ``speak_segment`` events.

    Uses *hold-one-ahead*: a sentence is not emitted the instant it arrives.
    It is held until the next sentence shows up — which proves the held one
    was not the last — then emitted with ``is_final=False``. After the stream
    ends, whatever is held is flushed with ``is_final=True``. This flags the
    final segment without an extra round-trip event, at the cost of one
    sentence's worth of latency on the *final* segment only (first-segment
    latency, which is what the user perceives, is unchanged).

    Returns the full concatenated response text.

    When ``voice`` is False (text-only mode) no ``speak_segment`` events are
    emitted at all — only ``transcript_delta`` for the on-screen subtitle.
    """
    base_turn_id = make_id()
    t0 = clock()
    seq = 0
    held_text: str | None = None
    held_seq: int | None = None
    sentences_seen: list[str] = []

    async def emit_segment(text: str, segment_seq: int, is_final: bool) -> None:
        segment_id = f"{base_turn_id}::{segment_seq}"
        record_segment(segment_id, text)
        await send_json(
            {
                "type": "speak_segment",
                "turn_id": segment_id,
                "base_turn_id": base_turn_id,
                "seq": segment_seq,
                "is_final": is_final,
                # Per-turn flags ride on the final segment only.
                "auto_continue": auto_continue if is_final else False,
            }
        )
        if log is not None:
            log(
                f"speak_segment base={base_turn_id} seq={segment_seq} "
                f"chars={len(text)} t_since_user={clock() - t0:.2f}s "
                f"final={is_final}"
            )

    async for sentence in sentences:
        sentences_seen.append(sentence)
        # On-screen subtitle behaviour is independent of voice segments.
        await send_json({"type": "transcript_delta", "text": sentence})
        if not voice:
            continue
        if held_text is not None:
            await emit_segment(held_text, held_seq, is_final=False)  # type: ignore[arg-type]
        held_text = sentence
        held_seq = seq
        seq += 1

    if voice and held_text is not None:
        await emit_segment(held_text, held_seq, is_final=True)  # type: ignore[arg-type]

    return " ".join(s.strip() for s in sentences_seen if s.strip())
