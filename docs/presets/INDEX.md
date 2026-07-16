# Donald Presets — Complete Documentation Index

Quick reference for all preset-related documentation and configuration.

---

## For Users (Want to Run a Preset?)

### **START HERE** 👇

1. **[QUICKSTART.md](./QUICKSTART.md)** — Get running in 10 minutes
   - Pick a preset (morning-ops | deep-research | trading-monitor)
   - Connect integrations (Gmail, Twilio, Alpaca, etc.)
   - Enable the preset
   - Test it
   - Cost expectations & troubleshooting

### Next Steps

2. **[README.md](./README.md)** — Complete preset documentation
   - What each preset does in detail
   - All configurable options
   - Example workflows
   - Integration requirements
   - Success metrics

3. **[DESIGN_RATIONALE.md](./DESIGN_RATIONALE.md)** — Why these presets? (context)
   - How we learned from OpenJarvis
   - Alignment with the masterplan
   - Cost & efficiency model
   - Future roadmap (preset marketplace)

---

## For Developers (Want to Build Presets?)

### Architecture & Concepts

1. **[IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md)** — Technical deep dive
   - Data model (PresetConfig, StageConfig, etc.)
   - Runtime execution (PresetExecutor, PresetScheduler)
   - CLI integration
   - Audit logging
   - Testing strategy
   - Deployment checklist

### Configuration Files

Located in `configs/presets/`:

- **[morning-ops.yaml](../../configs/presets/morning-ops.yaml)** (350 lines)
  - Email triage → Calendar scan → Market pre-open → Research digest
  - Scheduled (7am weekdays)
  - Cost: ~$0.23/day

- **[deep-research.yaml](../../configs/presets/deep-research.yaml)** (500 lines)
  - Configurable depth (quick/standard/deep)
  - Multi-phase: decompose → fan-out → fetch → verify → synthesize
  - On-demand or scheduled (weekly digest)
  - Cost: $0.15–$1.20 per research

- **[trading-monitor.yaml](../../configs/presets/trading-monitor.yaml)** (700 lines)
  - Three modes: paper → supervised live → autonomous
  - End-to-end: signal ingest → risk-check → backtest → execute → track
  - Continuous heartbeat (every 5 min during market hours)
  - Cost: ~$50–150/month

---

## File Overview

### Documentation (You are here)

| File | Purpose | Audience | Length |
|------|---------|----------|--------|
| `INDEX.md` (this file) | Navigation hub | Everyone | 1 page |
| `QUICKSTART.md` | Get running in 10 min | Users | 5 pages |
| `README.md` | Complete reference | Users + developers | 15 pages |
| `DESIGN_RATIONALE.md` | Why these presets? | Product/architecture | 8 pages |
| `IMPLEMENTATION_GUIDE.md` | How to build presets | Developers | 20 pages |

### Configuration

| File | Purpose | Audience | Editable? |
|------|---------|----------|-----------|
| `morning-ops.yaml` | Morning briefing preset | Users/developers | Yes |
| `deep-research.yaml` | Research preset | Users/developers | Yes |
| `trading-monitor.yaml` | Trading preset | Users/developers | Yes |

### Agent Specifications (Generated)

Located in `agent-specs/`:

- `morning-ops.md` — Auto-generated spec for email-triage agent
- `deep-research.md` — Auto-generated spec for research orchestrator agent
- `trading-monitor.md` — Auto-generated spec for risk-manager agent

(These are created when you `donald spawn` from a preset, documenting the agent that was created.)

---

## Common Questions

### "How do I enable a preset?"

→ [QUICKSTART.md](./QUICKSTART.md), Step 3

### "What does each stage cost?"

→ [README.md](./README.md), look for "Cost" section in each preset

### "Can I customize a preset?"

→ [README.md](./README.md), "Customization" section; edit the YAML in `configs/presets/`

### "How do I graduate from paper to real trading?"

→ [README.md](./README.md), "Trading Monitor" section, "Graduation criteria"

### "What integrations do I need?"

→ [QUICKSTART.md](./QUICKSTART.md), Step 2; or [README.md](./README.md), each preset's "Integrations required/optional"

### "How do I know if a preset is working?"

→ [QUICKSTART.md](./QUICKSTART.md), Step 4 (testing); [README.md](./README.md), "Metrics & Success"

### "Can I create my own preset?"

→ [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md), "Preset Config (YAML)" section; then run `donald presets test my-preset --dry-run`

### "How much will this cost me?"

→ [README.md](./README.md), each preset has a "Cost model" section; [QUICKSTART.md](./QUICKSTART.md), "Cost Expectations"

### "Why these three presets and not others?"

→ [DESIGN_RATIONALE.md](./DESIGN_RATIONALE.md), "The Three Presets (Why These Specific Three?)"

---

## Implementation Checklist (for developers shipping presets)

- [ ] Read [IMPLEMENTATION_GUIDE.md](./IMPLEMENTATION_GUIDE.md)
- [ ] Implement `PresetRegistry` class (load YAML configs)
- [ ] Implement `PresetExecutor` class (run stages in sequence/parallel)
- [ ] Implement `PresetScheduler` class (wire into cron/event scheduler)
- [ ] Add CLI commands: `donald presets list|run|test|enable|disable|metrics`
- [ ] Add audit logging for every preset run
- [ ] Write tests (unit + integration, with dry-run mode)
- [ ] Validate cost estimates match actual token usage
- [ ] Document in-repo

---

## Glossary

| Term | Definition |
|------|-----------|
| **Preset** | A predefined orchestration (YAML config) that runs a multi-stage workflow |
| **Stage** | One step in a preset (e.g., email-triage, market-scan) |
| **Skill** | A reusable capability that a stage calls (e.g., Gmail/read_inbox) |
| **Orchestrator** | The router that dispatches stages and manages orchestration flow |
| **Dry-run** | Execute a preset without side effects (no API calls, no real trades, no emails sent) |
| **Graduated autonomy** | Earning higher autonomy levels (paper → supervised → autonomous) via proven track record |
| **Hard limit** | A constraint that CANNOT be overridden (e.g., max daily loss for trading) |
| **Guardrails** | Approval gates, cost limits, kill switches, allowlists |

---

## Architecture Diagram

```
User Request
    │
    ├─ "Donald, run morning-ops"
    ├─ "Research SpaceX" (on-demand deep-research)
    └─ "Enable trading-monitor" (enable scheduling)
    │
    ▼
┌──────────────────────────────────────┐
│     Donald Core (Orchestrator)       │
│  • Intent router                     │
│  • Skill dispatcher                  │
│  • Tool-call loop                    │
│  • Memory/recall integration         │
└──────────────────────┬───────────────┘
                      │
┌─────────────────────▼───────────────────┐
│       Preset Runtime (NEW)              │
│  • Load preset YAML config              │
│  • Expand to execution DAG              │
│  • Execute stages in sequence/parallel  │
│  • Manage approval gates                │
│  • Log cost/duration/outcome            │
└─────────────────────┬───────────────────┘
                      │
┌─────────────────────▼──────────────────────┐
│        Skill Registry (existing)           │
│  • Email (Gmail)                           │
│  • Calendar                                │
│  • WebSearch / WebFetch                    │
│  • Market Data / Trading APIs              │
│  • Memory (Postgres + vector DB)           │
│  • Twilio (SMS/voice)                      │
│  • Google Drive / Canva / Miro             │
│  • ... (60+ skills)                        │
└────────────────────────────────────────────┘
                      │
┌─────────────────────▼──────────────────────┐
│     Integration Fabric (MCP + Composio)    │
│  • Gmail, Drive, Calendar                  │
│  • WebSearch, WebFetch                     │
│  • Alpaca, Polygon, other brokers          │
│  • Long-tail via Composio                  │
└────────────────────────────────────────────┘
```

---

## Roadmap: Preset Evolution

| Phase | When | What | Status |
|-------|------|------|--------|
| **Phase 0** | Now (Jul 2025) | 3 core presets (morning-ops, deep-research, trading-monitor) | ✅ Done |
| **Phase 1** | Aug 2025 | User testing, refinement, cost optimization | ⏳ Next |
| **Phase 2** | Sep 2025 | Community feedback, new presets (competitor-watch, podcast-digest) | 📅 Planned |
| **Phase 3** | Q4 2025 | Preset marketplace, version control, auto-updates | 📅 Planned |
| **Phase 4** | 2026+ | Preset composition (combine multiple presets), ML-based optimization | 🔮 Imagined |

---

## Related Documentation

- **[docs/00-MASTERPLAN.md](../00-MASTERPLAN.md)** — Donald's full strategic vision
- **[AGENT.md](../../AGENT.md)** — Orchestrator deep dive
- **[agent_factory/spec.py](../../agent_factory/spec.py)** — Agent spec generation
- **[agent_factory/models.py](../../agent_factory/models.py)** — Data model definitions

---

## Getting Help

- **Quick question?** → Check the FAQ in [QUICKSTART.md](./QUICKSTART.md)
- **How do I...?** → Search this INDEX for your question
- **Something's broken** → Run `donald diagnose --preset <name>`
- **Bug report** → See [CONTRIBUTING.md](../../CONTRIBUTING.md)

---

**Last updated:** July 1, 2025  
**Presets version:** 1.0  
**Donald version:** Phase 1 (Research Engine)
