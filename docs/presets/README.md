# Donald Preset Orchestrations

Presets are **production-ready, documented orchestration patterns** for common Donald workflows. They define:
- Which skills are needed
- Execution mode (scheduled, on-demand, continuous)
- Approval gates & guardrails
- Cost & latency expectations
- Memory & state management
- Success metrics & example invocations

Each preset is **independently shippable** and **composable** — you can run one or all three, and they share the same memory layer and orchestrator.

---

## The Three Presets

### 1. **Morning Operations** (`morning-ops`)

**What it does:** Daily 7am briefing with email summary, calendar conflicts, market pre-open, and tracked research updates.

**Execution:** Scheduled (weekday mornings) or on-demand.

**Components (run in sequence):**
1. **Email Triage** — Summarize inbox, flag urgent, draft VIP replies
2. **Calendar Scan** — Check today's conflicts, pull prep items
3. **Market Pre-Open** — Overnight gaps, portfolio status, >2% moves
4. **Research Digest** — New analysis on tracked companies

**Output:** Structured text + voice (via Twilio) + Drive document

**Cost:** ~$0.23/day (all stages) | **Duration:** ~4 minutes

**Guardrails:**
- Read-only (no approvals needed)
- Daily cost limit: $0.50
- Quiet hours: 10pm–8am (no SMS alerts)

**Integrations required:** Gmail, Google Calendar, Twilio, Google Drive

**Integrations optional:** Market Data (if trading enabled), Research module

**Example:**
```bash
# Enable: set config.yaml to enable morning-ops scheduling
# At 7am, Donald automatically:
# - Reads inbox, extracts 3 urgent items
# - Checks calendar, flags conflicts
# - Fetches overnight market gaps
# - Summarizes research updates
# - Sends SMS: "Morning brief ready. 3 urgent items, 1 calendar conflict."
```

---

### 2. **Deep Research** (`deep-research`)

**What it does:** Multi-source, adversarially-verified research producing 5–30 page cited dossiers.

**Execution:** On-demand or scheduled (weekly digest of tracked companies).

**Configurable depth levels:**
- **Quick** (2–3 min) → 1–2 page brief, $0.15, 5 key findings
- **Standard** (5–10 min) → 5–10 page briefing, $0.50, balanced evidence
- **Deep** (45 min – 1 hr) → 20–30 page dossier, $1.20, full data tables + appendices

**Multi-phase pipeline (fan-out where possible):**

```
decompose (break into sub-questions)
  ↓
fan_out (8 agents in parallel, each owns one angle)
  ├─ News & catalysts
  ├─ Financials (SEC filings)
  ├─ Competitive landscape
  ├─ Risks & headwinds
  ├─ Valuation
  ├─ Technicals (if tradeable)
  ├─ Expert commentary
  └─ Emerging signals
  ↓
fetch (pull full documents, not snippets)
  ↓
verify (single-pass cross-reference)
  ├─ flag single-source claims
  └─ surface contradictions
  ↓
adversarial_verify (3-agent debate, deep mode only)
  └─ try to refute each key claim
  ↓
synthesize (produce final briefing)
  ├─ executive summary
  ├─ thesis
  ├─ evidence (cited)
  ├─ counterarguments & risks
  └─ data tables
  ↓
appendix (optional, deep mode)
  └─ full financials, org charts, timeline
```

**Output formats:**
- Markdown (indexed in memory for semantic recall)
- PDF (via Google Drive)
- Canva deck (branded, shareable)
- HTML (embeddable)

**Memory & recall:**
```python
# Later, ask Donald:
"What did we conclude about SpaceX in March?"
# → vector search returns the dossier + key findings

"Show all research on AI infrastructure capex"
# → lists all dossiers tagged with entity "AI infrastructure"

"What contradictions did we find across our reports?"
# → queries memory for conflicts between sources
```

**Cost & latency model:**
| Depth | Duration | Cost | Quality |
|-------|----------|------|---------|
| quick | ~2 min | $0.15 | 5 findings, 1 source/claim |
| standard | ~5–10 min | $0.50 | 5–10 page, 2 sources/claim |
| deep | 45 min–1 hr | $1.20 | 20–30 page, 3+ sources, adversarial check |

**Guardrails:**
- Hard cost limits (quick: $0.20, standard: $0.75, deep: $1.50)
- Halt if >10 contradictions & ≤50% claims verified
- All read-only (no approvals)

**Integrations required:** WebSearch, WebFetch, Google Drive

**Integrations optional:** SEC EDGAR, News API, YouTube, Canva, Slack (via Composio)

**Examples:**
```bash
# On-demand, quick
donald research "SpaceX Starlink business model" --depth quick
# → 2-page brief in 2 min, $0.15

# On-demand, deep
donald research "Tesla FSD vs. Waymo: who's ahead?" --depth deep
# → 25-page dossier with financials, tech comparison, risk in ~45 min, $1.20

# Scheduled, weekly digest
# Every Monday 9am, automatically research your tracked companies
# Output: email + Drive docs (auto-archived with week stamp)
```

---

### 3. **Trading Monitor** (`trading-monitor`)

**What it does:** End-to-end orchestration for signal ingest, risk-checking, backtesting, execution, position tracking, and P&L reporting.

**Execution:** Continuous (heartbeat), on-demand (manual trades), scheduled (daily/weekly reports).

**Three modes (graduated autonomy):**

| Mode | Approval | Cost/trade | When |
|------|----------|-----------|------|
| **Paper** | None | $0.01 | Always available; learn & validate |
| **Supervised Live** | SMS approval, 5-min window | $0.02 | After paper ≥2 weeks, ≥20 trades, Sharpe >0.5 |
| **Autonomous Live** | None (hard limits instead) | $0.01 | After supervised ≥30 trades, track record >0.8 Sharpe |

**Signal ingest (three channels):**
1. **Manual** — "Donald, buy 10 NVDA"
2. **Webhook** — External model POSTs signal (symbol, side, size, confidence, horizon)
3. **Research-originated** — Research pillar proposes a trade

**Core pipeline:**
```
signal_ingest
  ↓
risk_check (hard limits: position size, daily loss, margin, etc.)
  ↓ REJECT if hard limit breached → alert & halt
  ↓
backtest (replay on 5y historical data; Sharpe, win rate, drawdown)
  ↓ WARN if Sharpe <0.3 → escalate or suggest adjustment
  ↓
strategy_size (Kelly fraction or % of portfolio sizing)
  ↓
approval_gate (mode-dependent)
  ├─ paper: auto-approve
  ├─ supervised: SMS approval required
  └─ autonomous: skip
  ↓ REJECT if timeout or user declines
  ↓
order_execution (place with Alpaca, idempotent)
  ↓
position_tracking (update P&L, entry price, current price, duration)
  ↓
alerting (notify on fill, >2% move, approaching loss limit)
```

**Heartbeat monitoring (continuous, every 5 min during market hours):**
- Poll broker for fills on pending orders
- Verify no position exceeded hard limits (auto-halt if so)
- Alert if any position moved >2%
- Update running P&L

**Hard limits (ALWAYS ON, cannot be waived):**
```yaml
paper:
  max_per_trade: unlimited (fake money)
  max_daily_loss: unlimited
  max_leverage: 3×

supervised:
  max_per_trade: $5,000 (you set)
  max_daily_loss: $10,000
  max_portfolio_drawdown: -20%
  max_leverage: 1× (no margin)

autonomous:
  max_per_trade: $2,500 (conservative; increase after proof)
  max_daily_loss: $5,000
  max_portfolio_drawdown: -10% (auto-halt)
  max_leverage: 1.5× (after 3 months)
  
# Plus:
kill_switch: sms "donald halt" → stops all trading instantly
banned_symbols: [list you control]
```

**Scheduled reports:**
- **Daily EOD** (4:30pm ET) — Total P&L, win rate, biggest winner/loser
- **Weekly** (Sunday 6pm) — Weekly P&L + Sharpe, trades by strategy, drawdown history
- **Monthly** (first Monday 8am) — Monthly return %, Sharpe, Sortino, tax lot summary, lessons learned

**Graduation criteria (mode progression):**
```
Paper → Supervised:
  ✓ ≥20 trades
  ✓ ≥2 weeks running
  ✓ Sharpe >0.5
  ✓ Max drawdown <-15%
  ✓ Your explicit approval

Supervised → Autonomous:
  ✓ ≥30 supervised trades
  ✓ ≥30 days running
  ✓ Track record strong (Sharpe >0.8, max dd <-10%)
  ✓ Zero policy violations
  ✓ Your annual re-approval
```

**Memory & recall:**
```
"What was my best trade last month?"
"Show me all TSLA trades and outcomes"
"What's my 3-month Sharpe on momentum signals?"
```

**Cost model:**
| Component | Cost |
|-----------|------|
| Per signal ingested | $0.01 |
| Per backtest | $0.15 |
| Per trade execution | $0.01 |
| Per alert | $0.005 |
| **Monthly estimate** | $50–150 (depends on frequency) |

**Guardrails:**
- Dry-run mode: "donald backtest NVDA BUY 100" (no execution, just analysis)
- Approval timeout: 5 minutes for SMS decision
- Kill switch: Always live
- Audit log: Every action, reasoning, outcome, fill details

**Integrations required:** Alpaca (or IBKR/Coinbase), Market Data, Database (Postgres)

**Integrations optional:** Twilio (SMS alerts), Slack, Google Drive, Canva (deck reports)

**Examples:**
```bash
# Paper trading
donald trade buy 100 NVDA
# → Backtest runs, fills simulate, P&L tracks
# → No real money; learning phase

# Supervised live (SMS approval gate)
donald trade buy 50 TSLA
# SMS arrives: "TSLA BUY 50 @ market. Risk: +$15k exposure. Backtest Sharpe: 0.7. Approve? Reply Y/N"
# You reply: Y
# → Real order placed, fills tracked, notified on completion

# Autonomous (after graduated)
# Every time research pillar proposes a trade, it's auto-executed (within hard limits)
# You're notified post-execution with fill details

# Scheduled report
# Every Sunday 6pm, email summarizes weekly P&L, Sharpe, best/worst trades
# + Drive doc with full analysis

# Kill switch
sms "donald halt"
# → All trading stopped immediately (existing fills still tracked)
```

---

## How to Use Presets

### Installation & Enablement

1. **Copy preset config to Donald:**
   ```bash
   cp configs/presets/morning-ops.yaml config.yaml  # or merge into existing
   ```

2. **Enable integrations** (one-time OAuth):
   ```bash
   donald mcp connect gmail
   donald mcp connect drive
   donald mcp connect calendar
   donald mcp connect twilio  # set API key in .env
   ```

3. **Test a preset:**
   ```bash
   # Morning ops: test email triage stage
   donald stage email-triage --dry-run

   # Deep research: test on a simple query
   donald research "What's happening with AI chips?" --depth quick

   # Trading: test backtest on a manual signal
   donald backtest NVDA BUY 50
   ```

### Composing Presets

Presets aren't mutually exclusive; you can run all three:

- **Morning-ops** runs daily at 7am (scheduled)
- **Deep-research** runs on-demand or weekly (you choose)
- **Trading-monitor** runs continuously (heartbeat every 5 min during market hours)

They share:
- The same orchestrator (Donald Core)
- The same memory layer (Postgres + pgvector)
- The same audit log
- The same approval gates & hard limits

Example orchestration graph:
```
Morning 7am:
  morning_ops → mentions "TSLA news" in market pre-open

Afternoon (on-demand):
  You ask: "Deep research on TSLA's strategy"
  deep_research → produces dossier, stores in memory

Later (autonomous):
  Research pillar proposes: "TSLA long, 3-month horizon"
  trading_monitor → risk-check → backtest → execute (if supervised approved)
  → notifies you of fill
  → daily report includes TSLA position
```

### Customization

Each preset is **intentionally data-driven** (YAML, not code) so you can:

1. **Adjust costs & latency:**
   ```yaml
   stages:
     email-triage:
       cost_estimate_usd: 0.05  # or 0.02 for faster, less careful
       latency_p99_seconds: 30
   ```

2. **Change approval gates:**
   ```yaml
   trading_monitor.modes.supervised:
     daily_spend_limit_usd: 10000  # increase your comfort level
   ```

3. **Add/remove integrations:**
   ```yaml
   integrations_optional:
     - Market_Data  # disable if you don't trade
     - Slack  # enable if you want trade alerts in Slack
   ```

4. **Adjust scheduling:**
   ```yaml
   morning_ops.scheduler.at_time: "06:00"  # earlier morning brief
   trading_monitor.heartbeat.interval_seconds: 120  # check more often
   ```

5. **Change output channels:**
   ```yaml
   morning_ops.output.channels:
     - type: email  # instead of SMS
       target: you@example.com
   ```

Then reload:
```bash
donald reload --preset morning-ops
```

---

## Integration Readiness

### Today (connected via MCP)
- ✅ **Gmail** — read inbox, draft/send
- ✅ **Google Calendar** — list events
- ✅ **Google Drive** — create/read/store docs
- ✅ **Twilio** — SMS & voice alerts
- ✅ **WebSearch & WebFetch** — open web research
- ✅ **Canva** — generate decks

### Phase 4 (wiring in)
- ⚙️ **Alpaca** — paper + live trading (via Composio or direct API)
- ⚙️ **Market Data** — quotes, bars, historical (Alpaca free tier or Polygon)

### Future (on-demand via Composio)
- 📋 **Yahoo Finance** — alternative stock data
- 📋 **SEC EDGAR** — faster filing pulls
- 📋 **News APIs** — structured news ingest
- 📋 **YouTube** — earnings call transcripts
- 📋 **Slack** — trade alerts, research sharing
- 📋 **Notion** — CRM sync

---

## Metrics & Success

Each preset logs:

- **Execution metrics:** duration, cost, latency
- **Quality metrics:** claims verified, contradictions flagged (research), Sharpe/drawdown (trading)
- **Outcome metrics:** emails sent, trades filled, research archived
- **Cost breakdown:** per stage, per pillar, monthly total

View with:
```bash
donald metrics --preset morning-ops
donald metrics --preset deep-research --period weekly
donald metrics --preset trading-monitor --mode paper
```

---

## Troubleshooting

**Issue:** "Integration not connected"
```
Solution: Run `donald mcp connect <name>` and complete OAuth
```

**Issue:** "Morning-ops crashes on email-triage stage"
```
Solution: Check Gmail API scope. Run: donald diagnose --preset morning-ops
```

**Issue:** "Deep-research is too expensive"
```
Solution: Lower depth (quick < standard < deep) or disable adversarial_verify:
  edit configs/presets/deep-research.yaml → set only_in_depth: [deep] for verify stage
```

**Issue:** "Trading-monitor backtests are slow"
```
Solution: Reduce historical window (default 5y) or use cheaper model:
  edit configs/presets/trading-monitor.yaml → trading.backtest.model: claude-haiku-4-5
```

---

## Next Steps

1. **Start with morning-ops** — simplest, most immediate value. Run for a week.
2. **Add deep-research** — run one on-demand research; see the dossier quality.
3. **Graduate to trading-monitor** — start in paper mode, build confidence over 2–4 weeks.

As you use each, Donald learns your preferences (memory layer) and optimizes automatically (Tier 6 hot-reload).

---

## See Also

- [00-MASTERPLAN.md](../00-MASTERPLAN.md) — Full strategic vision
- [agent_factory/spec.py](../../agent_factory/spec.py) — How agent manifests work
- [AGENT.md](../../AGENT.md) — Deep dive on orchestrator patterns
