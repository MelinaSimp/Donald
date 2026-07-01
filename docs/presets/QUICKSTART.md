# Donald Presets — Quick Start

Get a preset running in **10 minutes**.

---

## Step 1: Choose a Preset (pick ONE to start)

| Preset | Effort | Immediate Value | Prerequisites |
|--------|--------|-----------------|-----------------|
| **morning-ops** | Low | Daily automated brief | Gmail, Calendar, Twilio |
| **deep-research** | Medium | Research dossiers on demand | WebSearch, WebFetch, Drive |
| **trading-monitor** | High | Paper trading + backtests | Alpaca API key (free tier) |

**Recommendation:** Start with **morning-ops** — no new integrations, instant value, no risk.

---

## Step 2: Connect Integrations (one-time)

### For Morning-Ops:
```bash
# Authenticate Gmail, Calendar, Drive (single OAuth)
donald mcp connect gdrive
# This covers: Gmail, Google Calendar, Google Drive

# Set up Twilio (SMS alerts)
export TWILIO_ACCOUNT_SID=your_account_sid
export TWILIO_AUTH_TOKEN=your_token
export TWILIO_FROM_NUMBER=+1XXXXXXXXXX
```

### For Deep-Research:
```bash
# No new setup needed — WebSearch/WebFetch are built-in
# Optional: for SEC filings, news APIs, etc.
donald mcp connect composio
# (Then you can enable SEC EDGAR, NewsAPI, etc. on-demand)
```

### For Trading-Monitor:
```bash
# Get Alpaca API keys (free: https://alpaca.markets)
export APCA_API_KEY_ID=your_key
export APCA_API_SECRET_KEY=your_secret

# Verify Alpaca connection
donald backtest AAPL BUY 10 --paper  # should run instantly
```

---

## Step 3: Enable the Preset

### Copy or merge the preset into your config:

```bash
# Option A: Start fresh with the preset
cp configs/presets/morning-ops.yaml config.yaml

# Option B: Merge into existing config
# (manually add the preset sections to your config.yaml)
```

### Or edit `config.yaml` directly:

For **morning-ops**, add:
```yaml
presets:
  morning_ops:
    enabled: true
    scheduler:
      enabled: true
      at_time: "07:00"
      weekdays_only: true
```

For **deep-research**, add:
```yaml
presets:
  deep_research:
    enabled: true
    # Trigger on-demand only (no scheduler)
```

For **trading-monitor**, add:
```yaml
presets:
  trading_monitor:
    enabled: true
    mode: paper  # start in paper, never real money on day 1
    scheduler:
      enabled: true
      heartbeat_interval_seconds: 300
```

---

## Step 4: Test the Preset

```bash
# Test morning-ops email stage
donald stage email-triage --dry-run
# → Shows what would be in your morning brief, no actual sending

# Test deep-research on a simple query
donald research "What's new in AI chips?" --depth quick --dry-run
# → Generates a quick research brief, shows cost ($0.15)

# Test trading-monitor backtest
donald backtest NVDA BUY 100 --paper
# → Runs backtest on historical data, shows Sharpe/drawdown, doesn't execute
```

---

## Step 5: Run for Real

### Morning-Ops (automatic):
```bash
# Enable scheduler in config.yaml, then:
donald scheduler start

# At 7am tomorrow, Donald will:
# - Read your inbox
# - Check calendar
# - Fetch overnight market gaps
# - Summarize research updates
# - Send SMS: "Morning brief ready. 3 urgent, 1 conflict."
```

### Deep-Research (on-demand):
```bash
# Quick brief (2 min, $0.15)
donald research "SpaceX Starlink strategy" --depth quick

# Standard brief (5-10 min, $0.50)
donald research "Tesla FSD vs. Waymo" --depth standard

# Deep dossier (45 min, $1.20)
donald research "AI infrastructure capex trends" --depth deep
```

### Trading-Monitor (paper):
```bash
# Manual trade in paper mode
donald trade buy 100 NVDA
# → Backtest runs, simulated fill, position tracked, no real money

# Or feed it signals via webhook
curl -X POST http://localhost:8000/signals \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "TSLA",
    "side": "BUY",
    "size": 50,
    "confidence": 0.75,
    "reason": "earnings_beat"
  }'
# → Backtest, risk-check, simulated execute

# Daily report (every 4:30pm ET)
donald report trading --period daily
# → Shows P&L, win rate, biggest winner/loser
```

---

## Step 6: Iterate & Customize

After running a preset for 1–2 weeks:

1. **Check metrics:**
   ```bash
   donald metrics --preset morning-ops
   donald metrics --preset deep-research --period weekly
   donald metrics --preset trading-monitor --mode paper
   ```

2. **Adjust costs/latency** if needed:
   ```yaml
   # In config.yaml, adjust cost estimates or model tier:
   morning_ops.stages.email-triage.model: claude-haiku-4-5  # cheaper
   deep_research.phase.fan_out.model: claude-sonnet-5  # faster
   ```

3. **Modify scheduling:**
   ```yaml
   morning_ops.scheduler.at_time: "06:00"  # earlier
   trading_monitor.heartbeat.interval_seconds: 120  # check more often
   ```

4. **Graduate trading-monitor if ready:**
   ```yaml
   # After ≥2 weeks paper, ≥20 trades, Sharpe >0.5:
   trading_monitor.mode: supervised
   # Now SMS-approves each trade; real money, but you control it
   ```

5. **Enable more integrations** (on-demand):
   ```bash
   donald mcp connect slack  # for trade notifications
   donald mcp connect canva  # for research deck generation
   ```

---

## Preset Configuration Reference (Quick)

### Morning-Ops
| Setting | Default | How to Change |
|---------|---------|---------------|
| Time | 7:00am | `morning_ops.scheduler.at_time: "06:30"` |
| Weekdays only | true | `morning_ops.scheduler.weekdays_only: false` |
| Cost limit/day | $0.50 | `morning_ops.guardrails.cost_daily_limit_usd: 1.00` |
| Quiet hours | 10pm–8am | `morning_ops.guardrails.quiet_hours: {start: "23:00", end: "06:00"}` |

### Deep-Research
| Setting | Default | How to Change |
|---------|---------|---------------|
| Depth | standard | `donald research "..." --depth quick\|standard\|deep` |
| Cost limit/research | $0.75 (std) | `deep_research.guardrails.max_cost_per_research_usd.standard: 1.00` |
| Adversarial verify | on (deep only) | Only runs in deep mode; can't disable |
| Auto-archive | true | `deep_research.output.delivery.drive.retain_years: 5` |

### Trading-Monitor
| Setting | Default | How to Change |
|---------|---------|---------------|
| Mode | paper | `trading_monitor.mode: supervised` (after graduation) |
| Max per-trade (supervised) | $5,000 | `trading_monitor.guardrails.hard_limits.max_per_trade_usd.supervised: 10000` |
| Max daily loss | $10,000 | `trading_monitor.guardrails.hard_limits.max_per_day_loss_usd.supervised: 15000` |
| Backtest mode | 5 years | `trading_monitor.stages.backtest.lookback_days: 252` |

---

## Common Issues & Fixes

| Issue | Fix |
|-------|-----|
| "Gmail not connected" | Run `donald mcp connect gdrive` and complete OAuth |
| "Twilio SMS not received" | Check TWILIO_* env vars; verify number format |
| "Research too slow" | Lower depth: `--depth quick` instead of `--depth deep` |
| "Backtest crashes" | Ensure Alpaca API key is set; check `APCA_API_KEY_ID` |
| "Trading monitor won't execute" | Verify Alpaca connection with `donald backtest --paper` |

---

## Cost Expectations (Monthly)

| Preset | Frequency | Est. Monthly Cost | Notes |
|--------|-----------|-------------------|-------|
| **morning-ops** | Daily (22 days/mo) | ~$5 | Weekdays only; read-only |
| **deep-research** | 2 × standard/mo | ~$1 | On-demand; varies by depth |
| **trading-monitor** | 100 signals/mo | ~$30–50 | Paper trades, backtests, alerts |

**Total:** ~$40–60/mo for all three. Can dial down by switching to cheaper models (Haiku) or less frequent runs.

---

## Next Level

Once comfortable with one preset:

1. **Combine them:** Research proposes a trade → trading-monitor executes → morning-ops includes position in daily brief
2. **Add memory:** Donald remembers your trading rules, research preferences, approved vendors
3. **Autonomy:** Graduate trading-monitor to supervised, then autonomous within hard limits
4. **Custom presets:** Create your own orchestrations (e.g., "competitor-watch", "vc-signals")

See [README.md](./README.md) for full details.

---

## Support

- **Check logs:** `donald logs --tail 50`
- **Diagnose:** `donald diagnose --preset morning-ops`
- **Reset preset:** `donald reset --preset deep-research` (clears cache, re-runs test)

---

**Ready?** Pick a preset, run Step 1–4, and you're live. Report back what works!
