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
   *(Fact-store tier only today — roadmap M2.)*

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
| `web/` | Next.js UI — the seed for the marketing site and the desktop shell's renderer. |

Supporting: `security/` (auth, redaction, injection gate, audit), `config.yaml`,
`requirements*.txt`, `tests/`.

> **Agent-core status.** M0 collapsed three colliding agent packages
> (`donald/`, `src/donald/`, `wren/`) to **one** canonical `donald/`. The other two
> are in [`archive/`](./archive/README.md) with their best parts flagged for
> deliberate harvest (wren's integrations → M4; src/donald's tool framework,
> subagents, and self-knowledge → agent-core reconciliation). Test collection went
> from 100% red (0 tests ran) to **128 passing**.
>
> **Known drift — the next milestone (agent-core reconciliation).** `donald/` is
> itself a merge of divergent versions, so a handful of its own tests target APIs
> that the current files no longer expose. These are pre-existing (not caused by
> consolidation) and want a deliberate reconciliation pass, not a guess:
>
> - `test_core` / `test_proactive` expect a class `donald.agent.Agent`; `agent.py`
>   was overwritten with a functional personality loop (`respond()`).
> - `test_tools` expects a functional `donald.tools.execute(name, args) -> (out, err)`;
>   the current `donald.tools` exposes a `Registry` / `register_all` API instead.
> - `test_tools` / `test_memory` reference `workdir` / `home` fixtures that exist
>   nowhere in the tree — their defining conftest was lost in the merge.
>
> The reconciliation decides one agent-loop API for `donald/`, restores the missing
> fixtures, and folds in the src/donald framework where it's stronger.

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

Agent depth ≈ 80% · product shell ≈ 15%. A single-user local demo is essentially
here; a distributable, multi-tenant, signed, billed product is the work ahead. The
roadmap sequences that work into seven milestones (M0–M7).

## Integration strategy

Standardize on **MCP** (Model Context Protocol) so services become tools the agent
discovers, rather than hand-coded adapters. One **OAuth broker** stores per-user,
per-service tokens (encrypted) and every integration reuses it. `n8n`/Zapier act
as the long-tail escape hatch. Prioritize the 3–5 integrations the target user
actually lives in over a long shallow logo wall.
