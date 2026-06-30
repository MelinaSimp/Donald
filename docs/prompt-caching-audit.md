# Prompt-Caching Audit Runbook (Anthropic Messages API)

A diagnose-then-fix pass on prompt caching across an agent and its sub-agent team.
Each tier is independently shippable and verifiable against the `usage` numbers.

## The one rule

Caching is a **prefix match**. The cache key is the exact bytes of the rendered
request up to each `cache_control` breakpoint. One byte different at position N
invalidates every breakpoint at position ≥ N. Render order is fixed:

```
tools  →  system  →  messages
```

A breakpoint on the **last system block caches tools + system together**.

## Reference numbers

**Pricing (× base input price):** read ~0.1×, write 1.25× (5-min TTL) / 2× (1-h TTL), uncached 1×.
Break-even: 5-min TTL at 2 requests, 1-h TTL at 3.

**Minimum cacheable prefix** (below this, `cache_control` silently no-ops):

| Model | Minimum |
|---|---|
| Opus 4.8 / 4.7 / 4.6 / 4.5, Haiku 4.5 | 4096 tokens |
| Fable 5, Sonnet 4.6, Haiku 3.5 / 3 | 2048 tokens |
| Sonnet 4.5 / 4 / 3.7 | 1024 tokens |

**Breakpoints:** max 4 per request. Syntax:
`{"type": "ephemeral"}` (5-min) or `{"type": "ephemeral", "ttl": "1h"}` (1-h).
Top-level `cache_control` on `messages.create()` auto-places on the last cacheable block.

## Invalidation hierarchy

Changes invalidate their own tier and below only:

| Change | Tools | System | Messages |
|---|:---:|:---:|:---:|
| Tool defs (add/remove/reorder) | ❌ | ❌ | ❌ |
| Model switch | ❌ | ❌ | ❌ |
| `speed` / web-search / citations toggle | ✅ | ❌ | ❌ |
| System prompt content | ✅ | ❌ | ❌ |
| `tool_choice` / images / `thinking` toggle | ✅ | ✅ | ❌ |
| Message content | ✅ | ✅ | ❌ |

(✅ survives, ❌ busted.) `tool_choice` flips and `thinking` toggles keep the
tools+system cache — only tool-definition and model changes force a full rebuild.

## Phases

- **0 — Interview.** Map every `messages.create` / `.stream` call site: file:line,
  which agent, frequency. Find the shared tool-use loop. Grep `cache_control`.
  The load-bearing question: which system prompts interpolate a volatile byte.
- **1 — Baseline.** Sum month-to-date `input_tokens` (full price),
  `cache_creation_input_tokens` (writes), `cache_read_input_tokens` (reads).
  The number that matters is the full-price uncached share.
- **2 — Audit.** One row per call site: caches today?, cacheable prefix size
  (vs the model minimum above), silent invalidators, opt-out?, fix + priority.
  Biggest win = highest-frequency site with the largest uncached stable prefix.
- **3 — Shared sub-agent loop.** Pass system as a cached block; add a
  `cache_prompt: bool = True` opt-out for context-management agents.
- **4 — Conversation history.** Rolling breakpoint on the last message block
  (coexists with the system breakpoint — 2 of 4). Watch the 20-block lookback
  (place an intermediate breakpoint every ~15 blocks in long agentic turns).
- **5 — One-shots & volatile prompts.** Wrap static-system one-shots. For a
  volatile token in the system text, MOVE it into the first user message. Don't
  cache below the model minimum.
- **6 — Verify.** Re-pull the split; full-price share should fall, cache-read
  share should rise. Trust the day-or-two trend, not the blended month-to-date.

## Silent invalidators (grep the prefix-building path)

| Pattern | Why it breaks |
|---|---|
| `datetime.now()` / `Date.now()` / `time.time()` in system prompt | prefix changes every request |
| `uuid4()` / `randomUUID()` / request IDs early in content | every request unique |
| `json.dumps(d)` without `sort_keys=True` / iterating a `set` | non-deterministic byte order |
| session/user ID f-stringed into system prompt | per-user prefix, no sharing |
| conditional system sections (`if flag: system += ...`) | each combo a distinct prefix |
| `tools=build_tools(user)` varying per user | tools at position 0 → no cross-user cache |

Fix: move the dynamic piece after the last breakpoint, make serialization
deterministic, or delete it if not load-bearing.

## Reading usage

```
cache_creation_input_tokens   written this request (paid ~1.25x or 2x)
cache_read_input_tokens       served from cache (paid ~0.1x)
input_tokens                  uncached remainder ONLY (full price)
```

Total prompt = the sum of all three. `input_tokens` alone is not your prompt size.

- read == 0 across identical-prefix requests → silent invalidator (diff the bytes)
- high write share, low read share → writes expiring before reads → use `ttl: "1h"` or pre-warm

## Rules

- Diagnose before you fix (phases 0–2 produce numbers + a ranked plan).
- One tier per commit, one approval gate per tier.
- Never put volatile content in a cached prefix — it goes after the last breakpoint.
- Tool order and tool set must be stable; sort tools deterministically.
- Give every cached call an opt-out so one agent can't block caching for the team.
- Sparse traffic (< ~5 min between calls) → `ttl: "1h"` or a `max_tokens: 0` pre-warm.
