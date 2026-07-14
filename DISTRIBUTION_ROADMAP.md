# Distribution Roadmap — from "great agent" to "distributable product"

**Goal:** ship a Zoey-class product — a signed, self-updating desktop app that a
stranger can download, sign up for, pay for, connect their tools to, and have it
remember them across sessions.

**Where we are (2026-07):** the agent *brain* is ~80% done; the product *shell*
is ~15% done. Everything below is about closing the shell gap without rebuilding
the brain. The brain we keep: `orchestrator/` (routing, tool scoping, failure
isolation, confirmation gates, handoffs, hot-reload) + `wren/agent.py` (the tool
loop) + `gateway/` (model-agnostic streaming server).

The distance to Zoey is **not** more agent cleverness. It is seven unglamorous
systems: consolidation, a multi-user backend, real memory, a desktop shell, an
OAuth broker, billing, and code-signing. Each is its own slog. This doc sequences
them.

## Build status

Everything that can be built and verified in a headless environment is done and
tested (**219 tests green**, verified on SQLite and live Postgres). What remains
inherently needs a real build/signing machine and live third-party credentials.

| Milestone | Status |
|-----------|--------|
| M0 consolidate + agent-core reconciliation | ✅ done |
| M1 multi-user backend + authenticated gateway | ✅ done |
| M2 semantic memory (+ pluggable embedder, summarizer) | ✅ done |
| M3 **web** shell (Donald OS dashboard) | ✅ done (browser-verified) |
| M3 **desktop** wrapper (Tauri + auto-update) | 📄 documented — needs a build machine |
| M4 OAuth broker + integration use (connect → call provider) | ✅ done |
| M5 billing (Stripe subscriptions + signed webhooks) | ✅ done |
| M6 code-signing / notarization / update delivery | 📄 documented — needs certs |
| M7 hardening | ▶ partial (rate-limit, confirmation gates, audit, injection gate exist) |

The full product loop is demonstrable end to end: **sign up → dashboard →
per-user memory-aware chat → connect an integration and call it → upgrade to Pro.**
Setup for the two documented milestones is in [`DEPLOYMENT.md`](./DEPLOYMENT.md).

---

## The "distributable v1" definition of done

We are done with v1 when **a person we've never met can**:

1. Download a **signed, notarized installer** for macOS *and* Windows.
2. Launch it; the app **auto-updates** itself from our update endpoint.
3. **Sign up** (name / email / password / country / DOB / ToS) and **pay** via Stripe.
4. **Log in** from the desktop app via a browser OAuth/device-code flow.
5. **Connect** at least 3 real integrations (Google, Slack, GitHub) through a
   per-user OAuth broker — tokens stored encrypted, refreshed automatically.
6. Have the agent **remember them** across sessions (semantic recall + a durable
   profile), not just within one conversation.
7. Run all of the above **multi-tenant** — their data isolated from every other
   user — with per-user cost budgets and rate limits.

If any one of those seven is missing, it is not yet a distributable product. Today
we have #0 (a great agent) and partial credit on nothing else.

---

## Guiding decisions (make these first — they shape everything)

| Decision | Recommendation | Why |
|---|---|---|
| **Brand / name** | **Donald** (matches repo + branch) | Kill the sprawl: Wren, Drift AI, Trillion, Aether, Prism are all the same energy split six ways. One name. |
| **Agent core** | Keep `wren/agent.py` + `orchestrator/`, rename to Donald | It's the most complete loop with tools + confirmation + memory hooks. |
| **Desktop framework** | **Tauri 2** | Light binary, built-in updater + signing hooks, Rust core. Electron only if we later need a Node runtime *inside* the app. |
| **Backend language** | **Python** (FastAPI) | The agent is already Python. Don't split brains. |
| **DB** | **Postgres + pgvector** | One store for accounts, tokens, runs, *and* memory embeddings. Graduate to a dedicated vector DB only if recall volume forces it. |
| **Auth** | Browser device-code flow → token to app; **Clerk or WorkOS** to start | Don't hand-roll desktop auth first. Self-host later if needed. |
| **Billing** | **Stripe** Checkout + Customer Portal + webhooks | This *is* the pricing page. |
| **Integration standard** | **MCP** + one OAuth broker | Already have `wren/tools/mcp_base.py`. Every service reuses one auth flow. |

Lock these on day one. Re-deciding mid-build is where months go.

---

## Milestones

Each milestone ends in something demonstrable. `[P]` = parallelizable with a
second person. Durations assume one focused dev; halve the calendar with two.

### M0 — Consolidate to one product (1 week) — **do this first**

The single highest-leverage week. You cannot measure progress toward Zoey while
the repo is six half-products.

- Pick **Donald** as the one name; pick `wren/`+`orchestrator/`+`gateway/` as the
  one spine.
- Move `src/trillion`, the Aether cosmic-orb (`index.html`/`scene.js`/`package.json`),
  `prism`, `agent_factory`, and the Drift AI `north-star.md` into `/archive` (or
  delete). Keep git history; stop maintaining them.
- Collapse the ~10 `MCP_*.md` / `README_*.md` planning docs into **one**
  `PRODUCT.md` (what it is) + this roadmap (how we build it).
- Rename Wren → Donald in code/prompts, or formally declare "Wren is Donald's
  internal agent module" and stop using both names in user-facing copy.
- **Exit gate:** `git clone` → one obvious entry point, one name, one build path.

### M1 — Multi-user backend foundation (2–3 weeks)

Turn the single-user local server into a real backend. Everything else depends on
this.

- Stand up **Postgres**; schema for `users`, `sessions`, `workspaces`,
  `agent_runs`, `integration_tokens` (encrypted at rest), `memory_*` (M2 uses these).
- Wrap `gateway/server.py` as the product API: attach **auth middleware** (bearer
  token per request), scope every agent run and every tool call to a `user_id`.
- **Auth:** Clerk/WorkOS signup + login; issue tokens the desktop app will consume.
- Redis for sessions / rate-limit counters / the summarizer queue (M2).
- **Exit gate:** two different accounts hit the same server and cannot see each
  other's runs, tokens, or memory.

### M2 — Real memory (2–3 weeks) `[P]`

Replace `wren/memory.py`'s word-overlap store with the three-tier design you
already wrote in the plan but never built. This is the "feels alive" delta.

- **Semantic tier:** embed conversations/files/notes → pgvector; retrieve top-K by
  similarity per turn (RAG). This is the missing tier.
- **Profile/facts tier:** keep the JSON-fact idea but make it durable, deduped,
  versioned in Postgres.
- **Episodic summarizer:** a background job (cheap model) that, after each session,
  (a) updates the fact store and (b) writes a short episodic summary. Runs off the
  Redis queue.
- Per-turn injection = profile + top-K semantic hits + relevant facts, trimmed to
  the window.
- **Exit gate:** start a fresh session tomorrow; the agent recalls a fact and a
  past conversation without being re-told.

### M3 — Desktop shell (3–4 weeks)

The "it's an app you install" delta. None of this exists yet.

- **Tauri 2** app wrapping the React UI (reuse `web/` components; drop the three.js
  orb unless it's load-bearing for the brand).
- **Login** via browser device-code flow → token handed back to the app (M1 issues it).
- **Streaming chat UI** over the gateway **WebSocket** (`/ws` already streams
  delta/tool_call/tool_result/voice/final — reuse it).
- Local niceties: global hotkey, native notifications, file access.
- **Auto-updater** wired to an update endpoint (delivery infra lands in M6).
- **Exit gate:** a `.dmg` and `.msi` (unsigned for now) that install, log in, and
  chat against the real backend.

### M4 — OAuth broker + first 3 integrations (3–4 weeks, then ongoing)

Breadth, done once so every future integration is cheap.

- **One OAuth broker:** per-user, per-service token storage (encrypted, in Postgres
  from M1) with refresh handling. Every integration reuses it — do not hand-build
  auth per service.
- Productionize **Google, Slack, GitHub** end-to-end *multi-user* via MCP
  (`mcp_base.py` is the seam). Today's `~/.wren_oauth/` single-user flow is replaced.
- **Permission/confirmation UX** surfaced in the desktop UI (the Tier-4 gate already
  exists server-side — expose it).
- Wire **n8n/Zapier** as the long-tail escape hatch (n8n MCP is already available).
- **Exit gate:** a new user connects their own Google + Slack + GitHub from the app
  and the agent acts on their accounts with confirmation gates.

### M5 — Billing + signup + marketing (2–3 weeks) `[P]`

- **Stripe** subscriptions + Customer Portal + **webhooks** (the webhook handler is
  where subscription state actually lives — don't skip it).
- Full **signup flow**: name / email / password / country / DOB / ToS (Zoey's shape).
- **Pricing page** + landing SPA (the `web/` Next.js app is the seed).
- **Exit gate:** a stranger pays and gets a working, entitled account.

### M6 — Code-signing, notarization, update delivery (1–2 weeks calendar, more elapsed)

Unglamorous, mandatory, and the #1 cause of "why won't it install." Start the
paperwork early — certs have lead time.

- **Apple Developer ID** + notarization (mac); **Authenticode** cert (Windows).
- **Object storage** (S3/R2) for signed update artifacts; the
  `api/update/install/{mac,windows}` endpoint pattern (Zoey's literal fingerprint).
- Wire Tauri's updater to verify signatures against the channel.
- **Exit gate:** installers pass OS Gatekeeper/SmartScreen without warnings, and the
  app updates itself to a newer build.

### M7 — Hardening (ongoing, front-loaded before public launch)

- **Prompt-injection defense** — critical the moment the agent reads Slack *and* can
  send email. Content sanitization + confirmation gates on all side-effecting tools.
- **Cost control** — per-user token budgets, caching, model routing (cheap model for
  extraction/summary, strong model for reasoning).
- **Rate limits**, per-tool **audit logs** (audit log exists — extend per-user), and
  **run tracing/observability** on agent loops.
- **Exit gate:** a hostile Slack message cannot make the agent send money or email
  without an explicit human yes, and one user can't burn the whole token bill.

---

## Critical path & parallelization

```
M0 ─▶ M1 ─┬─▶ M3 ─────────────▶ M6 ─▶ (v1 launch)
          ├─▶ M4 ──────────────▶ M7 (front-load)
          └─▶ (M2 runs alongside; needs M1's DB)
M5 runs in parallel from M1 onward with a second person.
```

- **M1 is the gate.** Backend/DB unblocks M2, M3, M4, M5. Do it right after M0.
- **M2 and M5 are the natural parallel tracks** for a second person.
- **M6 is calendar-bound, not effort-bound** — begin the Apple/Windows cert
  paperwork during M3 so it's ready when the shell is.

---

## Realistic timeline

- **Private beta** (M0–M3 + M4's first integration, unsigned or dev-signed):
  **~8–11 weeks** solo.
- **Distributable v1** (all seven done-of-done items, signed, billed, multi-user):
  **~4–6 months** solo; **~3–4 months** with a second dev on the M2/M5 tracks.

The agent core being done is what makes this months, not a year — but billing,
integrations, signing, and safety are each a real slog, and none can be skipped.

---

## The "cannot skip" list (where months quietly go)

1. **OAuth broker** (M4) — every integration depends on it; build it once, first.
2. **Stripe webhooks** (M5) — subscription state is *defined* by them, not by Checkout.
3. **Signing/notarization** (M6) — long lead time, blocks distribution entirely.
4. **Prompt-injection defense** (M7) — non-optional the moment tools can both read
   untrusted content and take actions.
5. **Multi-tenant isolation** (M1) — retrofitting `user_id` scoping later is agony.

---

## First concrete steps (this week)

1. Approve the M0 consolidation (name = Donald, spine = wren+orchestrator+gateway).
2. Archive the parallel skeletons; collapse the planning docs into `PRODUCT.md`.
3. Stand up Postgres + the M1 schema stub (`users`, `integration_tokens`, `memory_*`).
4. Start the Apple Developer ID + Windows Authenticode paperwork in the background.
