# Donald Presets — Design Rationale

Why these three presets? How do they align with OpenJarvis learnings and Donald's masterplan?

---

## Context: Three Learnings from OpenJarvis

OpenJarvis, a local-first personal AI framework from Stanford, revealed three design patterns that apply equally to Donald (cloud-first with Claude):

1. **Formalized Presets** — Ship with well-documented preset configurations for common use cases (morning digest, deep research, code assistant). Users don't start from scratch; they start from a working example.

2. **Skills Framework** — Reusable, composable capability modules. OpenJarvis has ~150 skills from Hermes + 13.7k from OpenClaw. Donald needs a similar library so new orchestrations don't require new code.

3. **Evaluation as First-Class** — Track cost, latency, FLOPs, energy, and accuracy as core metrics. OpenJarvis treats these as constraints alongside correctness. Donald similarly should track `cost_usd`, `latency_p99`, `quality_score` for every stage.

**We applied all three to Donald.**

---

## The Three Presets (Why These Specific Three?)

### 1. Morning Operations (`morning-ops`)
**Addresses:** Pillar 3 (Business & Personal OS) — the *daily operational sync*.

**Why it's first:**
- **Immediate value** — no new setup beyond Gmail/Calendar (you already have these)
- **Low risk** — read-only, no approvals, no money moves
- **Builds muscle memory** — users learn Donald's interface on a routine task
- **Fast feedback loop** — 1-day iteration (daily briefing) vs. weeks (trading)

**Masterplan connection:** Phase 2–3 of the roadmap (memory + daily automation). Morning-ops is the heartbeat that keeps Donald engaged.

**OpenJarvis inspiration:** Directly adapted from their "morning-digest-mac" preset, which combines email, calendar, and news into a spoken briefing.

---

### 2. Deep Research (`deep-research`)
**Addresses:** Pillar 1 (Research) — the *multi-source, verified synthesis*.

**Why it's second:**
- **Builds on morning-ops** — research findings flow into the daily brief
- **Demonstrates orchestration** — multi-stage pipeline with fan-out parallelism and verification
- **High-value artifact** — produces something users actually share (10–30 page dossier)
- **Memory integration** — research is embedded and recalled later (semantic search)

**Masterplan connection:** Phase 1 (research engine). This is the "deep dossier" capability from the masterplan's vision.

**OpenJarvis inspiration:** Their "deep-research" preset uses structured decomposition → parallel web searches → synthesis. We adapted this with access to SEC filings (via Composio) and adversarial verification (unique to Donald's approach).

---

### 3. Trading Monitor (`trading-monitor`)
**Addresses:** Pillar 2 (Trading) — the *graduated autonomy loop*.

**Why it's third:**
- **Most complex** — builds on morning-ops (alerts) + deep-research (thesis) + core orchestrator (routing)
- **Highest stakes** — requires safety rails (hard limits, kill-switch, approval gates)
- **Longest iteration** — 2–4 weeks of paper trading before graduated autonomy
- **Highest ROI** — if it works, it's *actually making money*, not just generating alerts

**Masterplan connection:** Phases 4–5 (paper trading → supervised live → autonomous live). This preset embodies the "graduated autonomy" principle.

**OpenJarvis distinction:** OpenJarvis is local-first and focuses on efficiency per watt. Donald is cloud-first and focuses on capability per dollar. Trading is where the tradeoff is most visible: you need Claude Opus's reasoning for backtesting + risk management, not a local 7B model.

---

## Alignment with Donald's Masterplan

### Vision: "One agent for find out, trade, get it done"

| Masterplan Pillar | Preset | Status |
|---|---|---|
| **Pillar 1: Research** | deep-research | ✅ Ships fully |
| **Pillar 2: Trading** | trading-monitor | ✅ Ships with paper mode |
| **Pillar 3: Business OS** | morning-ops | ✅ Ships with email/calendar subset; expandable |

### Design Principles Encoded in Presets

| Principle | How Presets Embody It |
|-----------|------------------------|
| **Agentic, not chatty** | Each preset is a multi-stage orchestration, not a single turn |
| **Safety scales with consequence** | morning-ops: no approval; trading: SMS gate → autonomous |
| **Human-in-the-loop by default** | All presets start supervised or read-only; graduation earns autonomy |
| **Memory is first-class** | Each preset feeds into/recalls from semantic vector store |
| **Everything is auditable** | Every preset run logged: inputs, reasoning, cost, outcome |
| **Composable capabilities** | Presets are built from reusable skills; new presets reuse existing skills |
| **Provider-smart** | Presets choose models per stage (Opus for reasoning, Haiku for reads) |

### Architecture Layers (From Masterplan §2)

Presets sit at the **Skill Registry** level and above:

```
User Input (chat/web/CLI/voice)
         ↓
   Donald Core (Orchestrator + Scheduler)
         ↓
   ┌─────────────────────────────────┐
   │ Preset Runtime (NEW)            │ ← We're here
   │  - Load preset YAML             │
   │  - Execute stages               │
   │  - Log metrics & cost           │
   └─────────────────────────────────┘
         ↓
   ┌─────────────────────────────────┐
   │ Skill Registry (existing)       │
   │  - Gmail/read_inbox             │
   │  - Gmail/send_message           │
   │  - WebSearch/targeted_search    │
   │  - ... (60+ skills)             │
   └─────────────────────────────────┘
         ↓
   Memory & Knowledge (Postgres + pgvector)
   Scheduler (cron)
   Guardrails (approval, limits)
   Audit Log
```

---

## How Presets Enable Tier 6 Hot-Reload

Donald's Tier 6 (live hot-reload) means agents can change at runtime. Presets are the vehicle:

**Today (static):**
- Preset YAML in `configs/presets/`
- Developer updates YAML
- Admin restarts Donald
- New preset config is live

**Tomorrow (hot-reload, Tier 6+):**
- Watcher polls `configs/presets/` for changes
- Detects new/modified presets
- Re-registers with scheduler
- Next scheduled run uses new config
- No restart required

This is exactly Tier 6's model: *config is the agent*.

---

## Cost & Efficiency Model

Presets encode **OpenJarvis's insight** about constraints-as-first-class:

### Morning-Ops Cost Analysis
```yaml
stages:
  - email-triage:
      cost_usd: 0.05       # 50 emails × 1 token/email summary
      model: claude-opus   # careful reading
      latency_p99: 30s
  
  - calendar-scan:
      cost_usd: 0.02       # cheaper: just list + extract
      model: claude-haiku  # "scan" doesn't need reasoning
      latency_p99: 15s
  
  - market-open:
      cost_usd: 0.08       # fetch + analyze overnight gaps
      model: claude-opus   # reasoning needed for risk assessment
      latency_p99: 45s
  
  - research-digest:
      cost_usd: 0.06       # summarize tracked items
      model: claude-sonnet # balanced cost/quality
      latency_p99: 40s

Total: $0.21/day ≈ $6/month
```

**Key insight:** You don't run Opus everywhere. Each stage picks the right model for its job. This is what OpenJarvis calls "provider-smart."

---

## Iteration Path: From Masterplan to Presets

The masterplan defined **high-level pillars**. Presets make them **immediately executable**:

```
Masterplan Phase 1 (Research engine)
  "Deep, multi-source, fact-checked analysis"
         ↓
    (implementation detail)
         ↓
Preset: deep-research
  Stages: decompose → fan-out → fetch → verify → synthesize
  Example invocation: "Research SpaceX --depth deep"
  Output: 20-page dossier in Drive
```

Users don't need to read 40 pages of architecture docs. They run a preset, see it work, then iterate.

---

## Quality & Verification Strategy

Presets encode **quality gates** that are otherwise implicit:

### Morning-Ops Quality Gate
```yaml
# No formal gate, but:
# - Email triage summarizes 3–5 items max (prevents wall-of-text)
# - Calendar scan only surfaces conflicts (not all 10 meetings)
# - Market pre-open flags only >2% moves
# → Output is actionable, not overwhelming
```

### Deep-Research Quality Gate
```yaml
# Three-level verification:
verify:
  - level: single-pass (standard mode)
    rule: "Flag claims with <2 independent sources"
  
  - level: adversarial (deep mode)
    rule: "3 agents try to refute; if 2+ succeed → mark uncertain"
  
  - halt condition:
    rule: "If >10 contradictions AND <50% claims verified → abort, report issues"
```

### Trading-Monitor Quality Gate
```yaml
# Built into the risk manager:
backtest:
  halt_condition: "Sharpe <0.3 → escalate instead of execute"
risk_manager:
  hard_limits:
    - max_per_trade: $5,000
    - max_daily_loss: $10,000
    - max_portfolio_drawdown: -20%
    # These are NOT recommendations; they HALT trading if breached
```

---

## Memory Layer Integration

Presets feed into and retrieve from Donald's memory:

### Morning-Ops → Memory
```
"3 urgent emails + 1 calendar conflict"
  → stored in memory.inbox_items
  → tagged: {type: "email", urgency: "high", date: "2025-07-01"}
  → vector-embedded for later recall
```

### Deep-Research → Memory
```
"SpaceX dossier (20 pages, July 1, 2025)"
  → stored in memory.research_archive
  → embedded: can search "SpaceX funding" later and recall this dossier
  → tagged: {entity: "SpaceX", date_range: "2025-06-1..07-01", confidence: "high"}
```

### Trading-Monitor → Memory
```
"NVDA trade: BUY 100 @ $145, closed @ $148, +$300 P&L, 3-day hold"
  → stored in memory.positions (live state)
  → stored in memory.fills (immutable log)
  → query: "Show me all NVDA trades" or "What's my best trade this year?"
```

All three presets write to the same memory layer, creating a **unified knowledge base**.

---

## Future: Preset Marketplace

As Donald grows, users will want to **share and discover presets**:

```
Donald Preset Registry (imagined, Phase 6+)
  
  Community presets (GitHub)
  ├─ "competitor-watch" — research + alerts on competitor news
  ├─ "vc-signals" — monitor funding rounds, parse cap tables
  ├─ "podcast-digest" — summarize transcripts + extract key claims
  ├─ "twitter-monitor" — track mentions of your companies, sentiment
  └─ (user-contributed)
  
  Installation:
    donald presets install hermes:competitor-watch
    donald presets sync community --category research
```

This mirrors OpenJarvis's skill marketplace (Hermes, OpenClaw). Presets are the preset equivalent.

---

## Success Metrics for Presets

### Adoption (how many users run them)
- % of Donald instances with ≥1 preset enabled
- Most popular preset (likely morning-ops)
- Most valuable preset (likely trading-monitor for traders)

### Engagement (how often)
- morning-ops: daily (should be 22 runs/month for weekday users)
- deep-research: on-demand (avg frequency?)
- trading-monitor: continuous (5-min heartbeat)

### Quality (does it work?)
- morning-ops: "I act on 80%+ of flagged items" (user survey)
- deep-research: "Research findings change my decisions" + citation quality
- trading-monitor: "Backtests are accurate; supervised trades hit targets"

### Efficiency (does it cost what we said?)
- Actual cost vs. estimated cost (should be ±10%)
- Latency vs. p99 estimate
- Model tier appropriateness (Opus vs. Haiku where we claimed)

### Autonomy graduation (does trading-monitor earn trust?)
- % of paper traders who graduate to supervised
- % of supervised traders who earn autonomous tier
- Zero limit breaches (CRITICAL)

---

## Conclusion

Presets are the bridge between Donald's ambitious masterplan and a user who wants to start today.

They're **proven patterns** (adapted from OpenJarvis), **data-driven** (YAML, not code), **safe** (graduated approval gates), and **composable** (all built from the same skill registry).

Ship the three presets → users start with working examples → they iterate and customize → community contributes new presets → Donald becomes a platform.

---

## See Also

- [README.md](./README.md) — Full preset documentation
- [QUICKSTART.md](./QUICKSTART.md) — Get running in 10 minutes
- [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md) — For developers
- [docs/00-MASTERPLAN.md](../00-MASTERPLAN.md) — Donald's strategic vision
