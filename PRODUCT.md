# Donald — what it is

Donald is a **personal AI OS**: a desktop app backed by an agent with persistent
memory and a wide set of integrations. The goal is a "personal AI team" that
remembers you, adapts, and acts on your behalf across sessions.

This is the single **what-it-is** doc. For **how we get to a shippable product**,
see [`DISTRIBUTION_ROADMAP.md`](./DISTRIBUTION_ROADMAP.md).

## The four systems

Stripped of marketing, Donald is four systems that talk to each other:

1. **Desktop app** — what the user installs (macOS + Windows), with auto-update
   and login. *(Not built yet — see roadmap M3.)*
2. **Backend API** — accounts, billing, download/update delivery, and the broker
   for everything the app can't do locally. *(Prototype only — roadmap M1.)*
3. **Agent runtime** — the LLM loop that plans, calls tools, and produces answers.
   **This is the most complete part of the product.**
4. **Memory layer** — what makes the agent feel like it remembers and adapts.
   *(Three tiers landed — profile facts, semantic RAG chunks, episodic summaries —
   per-user, injected into each turn; see `backend/memory.py`. Real embedding
   provider and background summarizer are the remaining upgrades.)*

Integrations (Google, Slack, GitHub, Stripe, n8n, …) are tooling hung off the
agent runtime. The agent + memory are the depth; integrations are the breadth.

## The spine (active code)

The product is built from four modules. Everything else has been moved to
[`archive/`](./archive/README.md).

| Module | Role |
|--------|------|
| `donald/` | The agent core — agent loop, brain, memory, safety, voice, proactive daemon, personality. The brand-runnable app (`python donald.py`). |
| `orchestrator/` | Routing + the six-tier framework: smart dispatch, least-privilege tool scoping, failure isolation, confirmation gates, handoffs, hot-reload. |
| `gateway/` | The model-agnostic HTTP/WebSocket server — one endpoint the UI talks to; streams agent events; swappable model connectors (Anthropic, OpenAI-compatible, voice). |
| `backend/` | **M1** product API — accounts, auth (bearer sessions), per-user **encrypted** integration tokens, run history — plus the **M2** memory engine (`memory.py`, `embeddings.py`): per-user 3-tier semantic memory. Multi-tenant by construction; SQLite for dev/tests, Postgres in prod. See [`backend/README.md`](./backend/README.md). |
| `webui/` | The **web shell** — a static, build-free chat client (login → per-user streaming chat → integrations) served by `serve.py` at `/app`. The runnable UI a desktop (Tauri) shell will later wrap. |
| `serve.py` | The combined server: backend API + authed gateway + web shell in one process. |
| `web/` | Next.js UI — an alternate/marketing seed. |

Supporting: `security/` (auth, redaction, injection gate, audit), `config.yaml`,
`requirements*.txt`, `tests/`.

> **Agent-core status — reconciled.** M0 collapsed three colliding agent packages
> (`donald/`, `src/donald/`, `wren/`) to **one** canonical `donald/`; the other two
> are in [`archive/`](./archive/README.md) with their best parts flagged for
> deliberate harvest (wren's integrations → M4; src/donald's tool framework,
> subagents, and self-knowledge → a later feature pass).
>
> `donald/` was itself a merge of three divergent lineages. The reconciliation:
>
> - **Restored the `Agent` conductor** (`donald/agent.py`) — the tool-use loop over
>   `Brain` + `Registry` that `app.py` and the tests expect. A stray personality
>   `respond()` had overwritten it, breaking the runnable app *and* `test_core`.
> - **Resolved the `voice.py` vs `voice/` package shadow** — the graceful-degradation
>   speaker now lives at `donald/voice/speaker.py` and re-exports cleanly; the
>   voice-loop's stale `Conversation` import is deferred to call time.
> - **Archived orphan tests** (`test_config`/`test_memory`/`test_tools`) that
>   described an alternate design (JSON `~/.donald` config, functional `execute()`
>   tools, markdown memory) whose implementation was never merged and which
>   conflicts with the canonical runtime `test_core` covers. Revisit if we adopt
>   that config/tools design deliberately.
>
> Result: test collection went from **100% red (0 tests ran)** to **157 passing,
> 0 failing**, and `python donald.py` builds and drives a real tool loop again.

## Design principles (from the agent core)

- **The orchestrator is a router, not a worker** — it decides *who* and *whether*,
  then gets out of the way.
- **Least privilege by default** — an agent holds exactly the tools its job needs.
- **Bound everything** — every loop has a max iteration count, every call a token
  ceiling, every agent a declared model.
- **Agents propose, humans dispose** — anything consequential (send money, delete,
  post publicly) stops and asks. The human is the circuit-breaker.
- **Memory is data, never commands** — a stored note that reads like an order is
  still subject to the confirmation gate.
- **Pass references, not payloads** — handoffs carry paths/IDs/URLs, not blobs.

## Current honest state

Agent depth ≈ 80%. Product shell: **M0** (consolidation) + agent-core
reconciliation done; **M1** landed — multi-tenant accounts, bearer auth, encrypted
per-user integration tokens, and an authenticated gateway that scopes and records
each chat per user; **M2** landed — per-user 3-tier semantic memory injected into
each turn. Both verified on SQLite and live Postgres. A **web shell** (`webui/`,
served by `serve.py`) now makes it usable end to end — signup/login → per-user
streaming chat → integrations — verified in a real browser. Still ahead: wrapping
that shell in a Tauri desktop app with auto-update (the rest of M3), the OAuth
broker (M4), billing (M5), and signing (M6). The roadmap sequences M0–M7.

## Integration strategy

Standardize on **MCP** (Model Context Protocol) so services become tools the agent
discovers, rather than hand-coded adapters. One **OAuth broker** stores per-user,
per-service tokens (encrypted) and every integration reuses it. `n8n`/Zapier act
as the long-tail escape hatch. Prioritize the 3–5 integrations the target user
actually lives in over a long shallow logo wall.
