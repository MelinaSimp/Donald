# Donald — Voice Agent Latency Reference

A minimal, runnable voice-agent that **pipelines LLM streaming with TTS** so the
first audible word arrives within ~1s of the user finishing — instead of the
4–8s of dead air the default sequential architecture produces.

This is a greenfield reference build (the repo started empty). The stack was
chosen as sensible, well-documented defaults; every piece is swappable.

## The fix, in one sentence

Stop waiting; start streaming. The LLM emits sentences as it generates them, and
each sentence is turned into audio and played the moment it's ready — while the
LLM is still producing the rest of the response.

```
user stops → STT → LLM stream ─sentence 1→ TTS → bytes ─┐
                              ├─sentence 2→ TTS → bytes ─┤→ client audio queue → play
                              └─sentence N→ TTS → bytes ─┘
```

The two gates that cause dead air are *designed out* here:

- **Bottleneck A (server LLM-complete gate)** never exists: the server emits a
  `speak_segment` event per sentence via `stream_with_segments`
  ([`server/segment_stream.py`](server/segment_stream.py)) instead of buffering
  the whole reply before calling TTS.
- **Bottleneck B (client full-blob wait)** never exists: the client keeps an
  ordered audio queue and fetches/plays one short sentence at a time
  ([`client/audio-queue.js`](client/audio-queue.js)).

The **hold-one-ahead** pattern flags the final segment (`is_final=true`) without
an extra protocol event — a held sentence is only emitted once the next one
proves it wasn't last.

## How the interview maps to this build

The original prompt says "interview me first." This repo was empty, so there was
no existing stack to interview about — instead these are the deliberate choices,
all overridable in [`server/config.py`](server/config.py):

| Interview question | Choice here |
| --- | --- |
| Server language/framework | Python + FastAPI; voice loop is the `/ws` WebSocket |
| LLM provider/SDK, streaming? | Anthropic Claude, official SDK, **streaming**, thinking off (TTFT). Sentence boundaries split client-side in `iter_sentences` |
| TTS provider, streams bytes? | Pluggable; `mock` (offline) or `openai` (streaming MP3). `synthesize()` returns an async byte iterator |
| Transport | WebSocket for events + HTTP `StreamingResponse` for audio |
| Client audio architecture | `<audio>` element fed by an ordered queue; per-segment fetch |
| Tool-use loop? | None in this reference (text/voice turn only) |
| Where's the dead air? | Removed by design — see the two bottlenecks above |
| VAD threshold | `VAD_SILENCE_MS=900` (advisory; input here is typed — wire into your STT/client VAD) |

## Run it (no keys needed)

```bash
pip install -r requirements.txt
./run.sh                       # mock LLM + mock TTS, fully offline
# open http://localhost:8000, type a message, watch segments stream + play
```

Then layer in the real services:

```bash
ANTHROPIC_API_KEY=sk-... ./run.sh                          # real Claude streaming
TTS_PROVIDER=openai OPENAI_API_KEY=sk-... ANTHROPIC_API_KEY=sk-... ./run.sh
```

The mock TTS produces **silent** WAVs sized to each sentence — you won't hear
words, but playback, queueing, chaining, and interrupt all exercise correctly,
and the server logs the headline metric for every segment:

```
speak_segment base=... seq=0 chars=27 t_since_user=0.42s final=False
```

`seq=0 final=False` `t_since_user` is the number that matters — time to the
first spoken sentence. Target: under ~1s for short replies.

## Test

```bash
pytest
```

Covers the segment protocol structurally: single-sentence → one `is_final`
segment; multi-sentence → N segments with `is_final`/`auto_continue` only on the
last and `seq` 0..N-1; one shared `base_turn_id`; text-mode emits zero
`speak_segment` events; plus the sentence splitter (abbreviations, decimals,
token-by-token, tail flush).

## What to tune next (per the original brief)

1. **Confirm TTS actually streams on the wire** (some SDKs buffer internally).
2. **Drop LLM TTFT** — set `LLM_MODEL=claude-haiku-4-5` or
   `claude-sonnet-4-6`; for voice, time-to-first-token beats throughput.
3. **Direct-streaming playback** on the client instead of a per-segment blob.
4. **Pre-warm / persist the TTS connection** if your provider supports it.
5. **Tune VAD last** — the streaming work is the big lever; VAD is a refinement.

## What this reference deliberately does *not* do

- No parallel server-side TTS tasks (client-driven sequential playback is
  simpler and almost as fast).
- No partial-sentence/token streaming to TTS (sentence boundaries are the right
  granularity).
- No long-term storage of audio bytes (TTL'd in-memory segment text only).
