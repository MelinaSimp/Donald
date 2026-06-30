# Donald — Master Plan

> **Donald** is a personal, always-on AI operator: a single agent you delegate to for **deep research**, **trading** (supervised and autonomous), and **running your business and personal life**. Think of it less as a chatbot and more as a chief-of-staff + analyst + execution desk that never sleeps.

This document is the authoritative plan. It is deliberately exhaustive. Read sections in order the first time; after that, jump to the pillar or phase you care about.

---

## 0. TL;DR (read this first)

- **What it is:** An orchestrator agent ("Donald") built on the **Claude Agent SDK**, with a memory layer, a scheduler for autonomous tasks, a guardrails/approval layer, and a growing set of **capability modules** ("skills") that wrap real-world tools.
- **Three pillars:**
  1. **Research** — deep, multi-source, fact-checked analysis far beyond a single chat answer (e.g. *"What's really going on with SpaceX / Tesla / a stock?"* → a 10–30 page cited briefing).
  2. **Trading** — ingest your signal/"call stream" model, fetch market data, backtest, place orders through a brokerage API, manage risk, run **paper → supervised-live → autonomous** with hard safety rails.
  3. **Business & Personal OS** — email, outreach (Apollo → 50 cold emails), CRM, content (Canva/Higgsfield/Motion video), docs (Drive), calendar/tasks, SMS/voice (Twilio). Donald is the base layer everything routes through.
- **Already wired up (via MCP):** Apollo, Gmail, Google Drive, Canva, Higgsfield, Motion, Miro, Twilio, Composio (universal connector → brokerages, market data, Notion, Slack, etc.), GitHub.
- **Build order:** Foundation (agent core + memory + safety) → Research → Business OS → Trading (paper) → Trading (live, gated) → Autonomy & voice.
- **You need to decide 6 things** before we cut code — see [§12 Decisions I need from you](#12-decisions-i-need-from-you).

---

## 1. Vision & operating principles

**Vision.** One agent, "Donald," that you can hand any of three kinds of work: *find out*, *trade*, *get it done*. It works while you sleep, asks before doing anything irreversible or expensive, keeps a memory of you and your goals, and produces output a normal chat assistant can't — because it can run for hours, call dozens of tools, cross-check itself, and act in the real world.

**Principles (these drive every design choice):**

1. **Agentic, not chatty.** Donald plans, fans out work to sub-agents, verifies, and synthesizes. Long-horizon tasks are normal, not exceptions.
2. **Safety scales with consequence.** Reading data = no friction. Sending an email = low friction. Spending money / placing a live trade = explicit, logged, reversible-where-possible, and gated by hard limits. (See [§8 Safety](#8-safety-guardrails--trust).)
3. **Human-in-the-loop by default, autonomy by graduation.** Every capability starts supervised. It earns autonomy only after it proves itself (e.g. paper-trading track record, dry-run email batches).
4. **Memory is a first-class feature.** Donald remembers your goals, preferences, past research, positions, and people. Statelessness is the enemy.
5. **Everything is auditable.** Every action (especially trades and outbound messages) is logged with inputs, reasoning summary, and outcome. You can always answer "why did Donald do that?"
6. **Composable capabilities.** New powers are added as self-contained "skill" modules, not by rewriting the core.
7. **Provider-smart.** Use the most capable Claude models for reasoning/synthesis; use cheap/fast tiers for mechanical sub-tasks; use specialist services (Higgsfield/Motion for media) instead of reinventing them.

---

## 2. System architecture (the big picture)

```
                              ┌─────────────────────────────────────────────┐
        You ───────────────▶  │                 INTERFACES                   │
   (chat / web / CLI /         │  Claude Code · Web app · CLI · Telegram/SMS  │
    voice via Twilio)          │  · Email replies · Scheduled triggers        │
                              └───────────────────────┬─────────────────────┘
                                                      │
                              ┌───────────────────────▼─────────────────────┐
                              │             DONALD CORE (orchestrator)        │
                              │  • Intent router  • Planner  • Sub-agent fanout│
                              │  • Skill registry • Tool-call loop            │
                              │  (Claude Agent SDK)                           │
                              └───┬───────────┬───────────┬───────────┬──────┘
                                  │           │           │           │
              ┌───────────────────▼┐ ┌────────▼─────┐ ┌───▼────────┐ ┌▼───────────────┐
              │  MEMORY & KNOWLEDGE │ │   SCHEDULER  │ │ GUARDRAILS │ │   AUDIT LOG     │
              │  • Profile/prefs    │ │  (cron jobs, │ │ • approval │ │ • every action  │
              │  • Vector store     │ │   watchers,  │ │   policies │ │ • reasoning     │
              │  • Positions/CRM DB │ │   triggers)  │ │ • limits   │ │ • outcomes      │
              └─────────────────────┘ └──────────────┘ └────────────┘ └─────────────────┘
                                  │
        ┌─────────────────────────┼───────────────────────────────────────────┐
        │                         │                                           │
 ┌──────▼───────┐        ┌────────▼─────────┐                       ┌─────────▼──────────┐
 │  PILLAR 1     │        │   PILLAR 2        │                       │   PILLAR 3          │
 │  RESEARCH     │        │   TRADING         │                       │   BUSINESS/PERSONAL │
 │  • web search │        │  • mkt data feed  │                       │  • Gmail            │
 │  • fetch/read │        │  • signal ingest  │                       │  • Apollo outreach  │
 │  • verify     │        │  • backtest       │                       │  • Canva/Higgsfield │
 │  • synthesize │        │  • order exec     │                       │    /Motion content  │
 │  • report     │        │  • risk mgr       │                       │  • Drive/Docs       │
 └──────────────┘        │  • portfolio      │                       │  • Twilio SMS/voice │
                         └───────────────────┘                       │  • CRM / tasks      │
                                                                      └─────────────────────┘
                                  │
                         ┌────────▼──────────────────────────────────────────┐
                         │  INTEGRATION FABRIC (MCP + Composio)                │
                         │  Apollo · Gmail · Drive · Canva · Higgsfield ·      │
                         │  Motion · Miro · Twilio · GitHub · Composio (long   │
                         │  tail: Alpaca/IBKR, market data, Notion, Slack…)    │
                         └─────────────────────────────────────────────────────┘
```

### Core components

| Component | Responsibility | Tech |
|---|---|---|
| **Donald Core** | Routes intent, plans, spawns sub-agents, runs the tool loop, synthesizes results | Claude Agent SDK (TypeScript or Python) + Claude Opus for reasoning, Haiku/Sonnet for cheap sub-tasks |
| **Skill registry** | Self-contained capability modules Donald can invoke; each declares when to use it, inputs, and required tools | Folder of skill defs (mirrors Claude Code skills) |
| **Memory & knowledge** | Durable user profile, preferences, long-term facts, research archive, positions, contacts | Postgres (structured) + pgvector or a managed vector DB (semantic recall) |
| **Scheduler** | Recurring/triggered autonomous runs (daily research digest, market-open routine, email follow-ups) | Cron jobs / a queue (e.g. Temporal or a simple job runner) |
| **Guardrails** | Approval policies, spend/exposure limits, dry-run modes, kill switch | Policy module evaluated before any "write" or "spend" action |
| **Audit log** | Immutable record of every action with reasoning + outcome | Append-only table + exportable report |
| **Integration fabric** | The actual tools Donald can touch | MCP servers (already connected) + Composio for the long tail |

---

## 3. Pillar 1 — Research

**Goal:** When you say *"Figure out what's going on with SpaceX / a stock / a market / a competitor,"* Donald returns a depth of analysis a single chat reply cannot — multi-source, cross-checked, cited, and structured, in minutes to an hour.

### What "deep" actually means here
Donald runs a **research harness**, not a single prompt:

1. **Scope & decompose** — Turn your question into sub-questions (financials, news/catalysts, sentiment, competitive landscape, risks, valuation, technicals if it's a tradeable asset).
2. **Fan out** — Launch parallel sub-agents, each owning a sub-question and a search angle (news, filings, social/sentiment, expert commentary, primary data). Different angles catch what one search misses.
3. **Fetch & read primary sources** — Don't stop at snippets. Pull SEC filings (10-K/10-Q/8-K), earnings transcripts, official blogs, datasets. (Private co. like SpaceX → funding rounds, contracts, launch cadence, satellite/Starlink metrics, valuation marks from secondary markets.)
4. **Adversarially verify** — A separate pass tries to *refute* each key claim; low-confidence or single-source claims are flagged or dropped. This is the step that kills plausible-but-wrong conclusions.
5. **Synthesize** — Produce a structured briefing: executive summary → thesis → evidence → counter-thesis/risks → data tables → sources. Every non-obvious claim is cited.
6. **Deliver & archive** — Output as a doc (Google Drive / Markdown / Canva-formatted deck if you want it pretty), and store in Donald's memory so future questions build on it.

### Output formats you can ask for
- **Quick brief** (1–2 pages) — fast read.
- **Deep dossier** (10–30 pages) — the "go crazy" version with appendices and data tables.
- **Deck** — auto-formatted via Canva for sharing.
- **Living report** — Donald re-runs it on a schedule and tells you only what changed.

### Building blocks (mostly available today)
- `WebSearch` + `WebFetch` for the open web; the existing **deep-research skill** as the starting harness.
- **Google Drive** MCP to write/store reports.
- **Canva** MCP to produce decks.
- **Composio** to add specialist data (financial APIs, news APIs, SEC EDGAR) where the open web isn't enough.
- **Miro** to lay out research maps / relationship diagrams when visual.

### Phase-1 deliverable for Research
A `research` skill that: takes a topic + depth level, runs the fan-out/verify/synthesize loop, and returns a cited report saved to Drive — with an option to schedule it as a recurring digest.

---

## 4. Pillar 2 — Trading

> ⚠️ **This pillar touches real money and is regulated.** The plan below is engineering, not financial or legal advice. We build it **safety-first**: paper trading proves the system before a single live dollar, hard limits cap downside, and autonomous live trading is the *last* thing we enable, only with your explicit, repeated sign-off. See [§8](#8-safety-guardrails--trust).

**Goal:** You can (a) tell Donald to place a specific trade, (b) feed Donald your **prediction / "call stream" model** and have it execute trades off those signals, and (c) eventually let it trade **autonomously** within strict, pre-agreed risk limits.

### The trading stack

```
Your signal model / "call stream"  ─┐
Manual instruction ("buy 10 X")     ─┼──▶  SIGNAL INGEST ──▶ STRATEGY/POLICY ──▶ RISK MANAGER ──▶ ORDER ROUTER ──▶ Broker API
Donald-generated thesis (from       ─┘         │                  │                  │                 │
  Research pillar)                             │                  │                  │                 ▼
                                               ▼                  ▼                  ▼            Fills/positions
                                         MARKET DATA         BACKTESTER        POSITION/PNL ──────────────┘
                                         (quotes, bars)      (validate)        TRACKER
```

### Components

1. **Market data feed** — Real-time + historical quotes/bars. Options: **Alpaca** (free-ish, US equities + crypto, great API, built-in paper trading), Polygon, or a feed via Composio. Used by research, backtesting, and execution.
2. **Signal ingest** — A defined contract for *how your model talks to Donald*. Three input modes:
   - **Webhook/file**: your call-stream model POSTs signals (symbol, side, size/confidence, horizon) to Donald, or drops them in a watched file/sheet.
   - **Manual**: "Donald, buy 10 shares of NVDA" in chat.
   - **Donald-originated**: Donald's own research thesis proposes a trade (always supervised at first).
3. **Strategy/policy layer** — Translates a signal into an intended order respecting position sizing rules (e.g. % of portfolio, max per name, Kelly-fraction cap).
4. **Backtester** — Before any strategy goes live, replay it on historical data. Reports win rate, drawdown, Sharpe, etc. No backtest, no live.
5. **Risk manager** (the most important module) — Pre-trade checks: max position size, max daily loss / drawdown kill-switch, max leverage, banned symbols, per-trade and per-day dollar caps, "no trades outside market hours unless flagged." Can **halt all trading** instantly.
6. **Order router** — Places/cancels/modifies orders via the broker API. Idempotent, retries safely, never double-sends.
7. **Position & P&L tracker** — Live portfolio state in Donald's memory; feeds the risk manager and your reports.

### Brokerage options (pick in §12)
- **Alpaca** — best developer experience, native paper + live, US stocks + crypto, commission-free. **Recommended starting point.**
- **Interactive Brokers (IBKR)** — broadest market/asset coverage (options, futures, intl), more complex API.
- **Crypto-only** (Coinbase/Kraken via Composio) — if your focus is crypto.
- **Tradier / others** — if options are central.

### Modes (graduated autonomy)
| Mode | What happens | When we enable it |
|---|---|---|
| **Paper** | Real signals, fake money, real data. Full logging. | Phase 4, immediately. Run for weeks. |
| **Supervised live** | Real money, but every order needs your one-tap approval (push/SMS). | After paper track record + you sign off. |
| **Autonomous live (bounded)** | Donald trades within hard limits without per-trade approval; you get notified; kill-switch always live. | Last. Only with explicit limits you set, and only for strategies that passed paper + supervised. |

### Phase-4 deliverable for Trading
Paper-trading end-to-end: ingest a signal (manual + webhook), risk-check it, route it to Alpaca paper, track the position, and report P&L. Backtester usable on demand.

---

## 5. Pillar 3 — Business & Personal OS

**Goal:** Donald is the base layer for everything you do — research a prospect, draft and send email, run outreach campaigns, make content, manage docs, and reach you/your contacts over SMS or voice.

### Capabilities (all integrations already connected)

| Job to be done | How Donald does it | Tool |
|---|---|---|
| **Cold outreach at scale** — "Send 50 emails to my list" | Pull/enrich contacts, draft personalized emails, queue into a sequence, send (with your approval on the first batch) | **Apollo** (search, enrich, sequences, campaigns) + **Gmail** |
| **Find people/companies** | Search Apollo's database, enrich with verified emails/phones | **Apollo** |
| **Email triage & drafting** | Read inbox, summarize, draft replies, send on approval | **Gmail** |
| **Content & creative** | Generate images, video, audio, ads, social clips; make decks | **Higgsfield** (image/video/audio/3D), **Motion** (video), **Canva** (decks/brand templates) |
| **Documents & files** | Create/read/store reports, proposals, sheets | **Google Drive** |
| **Whiteboarding / planning** | Diagrams, project maps, mind maps | **Miro** |
| **SMS & voice** | Text/call you with alerts (trade fills, research done, approvals); text contacts | **Twilio** |
| **CRM / pipeline** | Track contacts, deals, follow-ups | Apollo + Donald's memory DB |
| **Anything else** | The long tail — Notion, Slack, Calendar, HubSpot, Stripe, etc. | **Composio** (connect on demand) |

### Example end-to-end flows Donald will run
- *"Research this company, find the 50 best-fit decision-makers, write a personalized email to each referencing something specific, and send."* → Research pillar + Apollo + Gmail, with you approving the template and first 5 sends.
- *"Make a 30-second promo video for my product and a matching deck."* → Higgsfield/Motion + Canva.
- *"Every morning, text me a 5-bullet summary of my inbox and calendar, and anything urgent."* → Scheduler + Gmail + Twilio.

### Phase-3 deliverable for Business OS
A working "outreach" flow (Apollo search → enrich → personalized draft → Gmail send with approval gate) and an "email triage" flow, plus the Twilio alert channel used across all pillars.

---

## 6. Memory & knowledge layer

Donald is useless if it forgets you. This layer is built early (Phase 1) and used by all pillars.

- **Profile & preferences** — who you are, your goals, risk tolerance, writing voice, recurring people/companies, "always do X / never do Y" rules.
- **Semantic archive (vector store)** — every research report, decision, and important conversation, embedded for recall. *"What did we conclude about SpaceX in March?"* just works.
- **Structured state (SQL)** — positions, P&L history, CRM contacts, campaign status, scheduled jobs, audit log.
- **Working memory per task** — scratch space for a single run; promoted to long-term only when worth keeping.

**Tech:** Postgres + pgvector (one DB, structured + semantic) is the simplest robust choice. Embeddings via an embedding model; recall injected into Donald's context at the start of relevant tasks.

---

## 7. Autonomy, scheduling & triggers

What makes Donald feel alive: it acts without you having to ask each time.

- **Scheduled runs** — "Every weekday 7am: research digest + inbox summary + market pre-open brief." "Every Sunday: weekly P&L + pipeline report."
- **Watchers/triggers** — A signal hits the webhook → evaluate a trade. A VIP emails you → draft a reply and alert you. A stock moves >5% → run a quick research refresh.
- **Long-running jobs** — A deep dossier that takes an hour runs in the background and pings you (Twilio/email) when done.
- **Self-check-ins** — For multi-day tasks (a campaign, babysitting a trade thesis), Donald re-checks state on a cadence and reports only when something changed.

**Tech:** a job scheduler (cron for simple, Temporal/queue for reliable long-running + retries) feeding Donald Core with the same skill interface used interactively.

---

## 8. Safety, guardrails & trust

This is non-negotiable and built into the core, not bolted on. Friction is proportional to consequence.

| Action class | Examples | Policy |
|---|---|---|
| **Read** | Web search, read inbox, fetch market data | No friction. Logged. |
| **Low-stakes write** | Draft (not send), create internal doc, paper trade | Auto, logged. |
| **Outbound comms** | Send email, send SMS, post | Approve first batch / first instance; then allow within rules. Rate-limited. |
| **Spend / trade (live)** | Place a real order, purchase credits | Explicit approval per action (supervised) → bounded autonomy only after graduation. Hard caps always apply. |
| **Irreversible / bulk** | Delete data, mass-send, large order | Always confirm, show exactly what will happen. |

**Hard rails (always on, cannot be reasoned around):**
- **Spend & exposure limits** — per-trade $, per-day $, max drawdown → auto-halt; max emails/day; credit spend caps.
- **Kill switch** — one command/text halts all trading and outbound activity.
- **Dry-run mode** — every destructive/bulk/financial capability supports "show me what you'd do" first.
- **Allowlists** — banned trading symbols, approved sender domains, contact-list scoping.
- **Full audit log** — who/what/when/why/outcome for every action, exportable.
- **Secrets hygiene** — API keys in a secret manager, never in the repo or logs; least-privilege scopes per integration.

**Compliance note (trading):** automated trading has tax, regulatory, and broker-ToS implications. We keep complete records, we don't promise returns, and before live autonomous trading you confirm you understand the risk. This plan does not constitute financial advice.

---

## 9. Tech stack & repository layout

**Stack (proposed — confirm in §12):**
- **Language:** TypeScript (best Claude Agent SDK + MCP ergonomics) — or Python if you prefer for the trading/quant side. Could split: TS core, Python trading workers.
- **Agent runtime:** Claude Agent SDK; Claude Opus for reasoning/synthesis, Sonnet/Haiku for cheap sub-tasks.
- **Data:** Postgres + pgvector.
- **Scheduler:** start with cron-style; graduate to Temporal/queue for reliability.
- **Integrations:** MCP servers (connected) + Composio (long tail).
- **Hosting:** a small always-on VM/container (Fly.io/Render/Railway/your cloud) + the existing remote-execution environment for dev.
- **Secrets:** a secret manager (Doppler/1Password/cloud KMS).

**Proposed repo layout:**
```
Donald/
├── docs/                     # this plan + per-pillar specs + decision log
├── core/                     # orchestrator, intent router, planner, tool loop
├── memory/                   # profile, vector store, SQL models, migrations
├── skills/                   # capability modules (composable)
│   ├── research/
│   ├── trading/
│   │   ├── signals/  data/  backtest/  risk/  execution/  portfolio/
│   ├── outreach/             # Apollo + Gmail
│   ├── content/              # Canva + Higgsfield + Motion
│   └── comms/                # Twilio
├── scheduler/                # cron jobs, watchers, triggers
├── guardrails/               # approval policies, limits, kill switch
├── integrations/             # MCP + Composio adapters, auth
├── audit/                    # logging + report export
├── interfaces/               # CLI, web, webhook endpoints
└── config/                   # env, limits, allowlists, secrets refs
```

---

## 10. Phased roadmap

Each phase ships something usable. Estimates assume focused iterative work; we adjust as we go.

### Phase 0 — Foundations (this doc + scaffolding)
- ✅ This master plan.
- Repo scaffold (folders above), config, secrets manager, audit log skeleton, Postgres+pgvector up.
- Donald Core minimal loop: take an instruction, plan, call a tool, log it.
- **Exit:** Donald can answer a question and log the action end-to-end.

### Phase 1 — Research engine
- Research skill (fan-out → verify → synthesize → cited report to Drive).
- Memory: store reports + recall.
- Scheduling hook (recurring digest).
- **Exit:** "Research SpaceX in depth" → a real cited dossier in Drive.

### Phase 2 — Memory & autonomy backbone
- Full profile/preferences, vector recall across pillars, scheduler + Twilio alert channel.
- **Exit:** Donald remembers you and can run a daily scheduled job that texts you.

### Phase 3 — Business & Personal OS
- Outreach flow (Apollo → enrich → personalized draft → Gmail send w/ approval).
- Email triage; content generation (Canva/Higgsfield/Motion); Drive docs.
- **Exit:** "Send 50 personalized emails to this list" works end-to-end with guardrails.

### Phase 4 — Trading (paper)
- Market data, signal ingest (manual + webhook), strategy/sizing, backtester, risk manager, order router → **Alpaca paper**, position/P&L tracker, reports.
- **Exit:** Your call-stream model drives paper trades; you get fills + P&L; backtests on demand.

### Phase 5 — Trading (live, gated)
- Supervised live (per-order approval via SMS/push) → bounded autonomous after a paper+supervised track record and your explicit limits.
- **Exit:** Donald trades real money within hard limits, fully logged, kill-switch live.

### Phase 6 — Voice, polish & expansion
- Twilio voice ("call me with the morning brief"), richer interfaces, Composio long-tail integrations on demand, continuous hardening.

---

## 11. Costs (rough, monthly — refine after §12)
- **LLM usage** — biggest variable; deep research + trading reasoning are token-heavy. Budget tiering (Haiku/Sonnet for mechanical work) keeps this sane.
- **Market data** — free tier (Alpaca) to start; paid (Polygon) if you need depth.
- **Hosting + DB** — small ($20–100/mo range to start).
- **Integration credits** — Apollo, Higgsfield/Motion (media generation), Twilio (per-message/minute) are usage-based.
- We'll instrument spend per pillar and put it in your weekly report.

## 12. Decisions I need from you
These materially change the build. I'll proceed on the **bolded recommended defaults** if you don't override.

1. **Trading scope & broker** — **Alpaca, US stocks + crypto, paper-first.** Or IBKR / options / crypto-only?
2. **Autonomy ceiling for trading** — what are your hard limits (max per-trade $, max daily loss, max % of portfolio per name)? And is bounded-autonomous a goal, or supervised-only forever?
3. **Your "call stream" / prediction model** — how does it emit signals today (a script? a service? a spreadsheet?) so I design the ingest contract right.
4. **Primary interface** — **chat + SMS alerts via Twilio** to start, then web dashboard? Or do you want a phone-call/voice experience early?
5. **Language preference** — **TypeScript core (Python trading workers if needed)**, or all-Python?
6. **Where it runs / who else uses it** — just you, or a small team? Any cloud you already use (for hosting + secrets)?

## 13. Risks & how we manage them
- **Financial loss (trading):** paper-first, hard limits, kill switch, backtests, graduated autonomy.
- **Sending the wrong thing (outreach):** approval gates, dry-run, rate limits, allowlisted domains.
- **Hallucinated research:** adversarial verification, citations, confidence flags, single-source flagging.
- **Runaway cost:** spend caps, model tiering, per-pillar metering.
- **Security/secrets:** secret manager, least-privilege scopes, no secrets in repo/logs, audit log.
- **Over-automation / loss of control:** every capability starts supervised; you can always inspect "why," and the kill switch is absolute.

## 14. Success metrics (how we know Donald is working)
- **Research:** time-to-dossier; you act on its conclusions; "told me something I didn't know" rate.
- **Trading:** paper Sharpe/drawdown vs. benchmark; % signals executed correctly; zero limit breaches.
- **Business:** emails sent/replies booked; hours saved/week; tasks fully handled without you touching them.
- **Trust:** zero unauthorized irreversible actions; you let it do more over time.

---

### Appendix A — Capability ↔ integration map (what's ready today)
| Capability | Integration | Status |
|---|---|---|
| Web research | WebSearch/WebFetch + deep-research skill | ✅ available |
| Reports/docs | Google Drive | ✅ connected |
| Decks/brand design | Canva | ✅ connected |
| Image/video/audio/3D | Higgsfield | ✅ connected |
| Video production | Motion | ✅ connected |
| Diagrams/whiteboard | Miro | ✅ connected |
| Lead gen / outreach | Apollo | ✅ connected |
| Email | Gmail | ✅ connected |
| SMS / voice | Twilio | ✅ connected |
| Long-tail apps + brokerages/market data | Composio | ✅ connected |
| Code/repo ops | GitHub | ✅ connected |
| Trading broker (Alpaca/IBKR) | via Composio or direct API | ⚙️ to wire in Phase 4 |
| Market data feed | Alpaca/Polygon | ⚙️ to wire in Phase 4 |
| Memory DB (Postgres+pgvector) | self-hosted | ⚙️ to stand up Phase 0 |
