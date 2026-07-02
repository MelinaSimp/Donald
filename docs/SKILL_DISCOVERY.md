# Donald Skill Discovery Framework

Formalized skill specs so users can discover, install, and compose capabilities without code.

---

## Vision

Instead of:
```python
# Old: skills scattered in code, undocumented
orchestrator.call_skill("Gmail/read_inbox", ...)  # hope it exists, guess the params
```

Users get:
```bash
# New: discover, install, use
donald skills search email
donald skills install hermes:email-classifier
donald research "..." --use-skill email-classifier:draft
```

---

## Skill Specification (JSON Schema)

Every skill is a declarative YAML/JSON file:

```yaml
# skills/Gmail/read-inbox.yaml
---
spec_version: "1.0"
id: Gmail/read-inbox
name: "Read Inbox"
category: communications
description: >-
  Fetch and list emails from Gmail inbox, with optional filtering.
  Returns: list of {id, from, subject, preview, date, labels, has_attachment}

# Who provides this skill?
provider: Gmail                    # MCP server or integration name
integration_required: gmail         # must be connected
cost_estimate:
  tokens_per_call: 500
  usd_per_call: 0.01
  cache_friendly: true             # long results can be cached

# When should this be used?
when_to_use: |
  Use this skill to:
  - Check for new emails
  - Find emails from a specific sender
  - Triage by urgency or labels
  
  DON'T use this for:
  - Reading full email bodies (use Gmail/read-message)
  - Sending emails (use Gmail/send-message)

# Input contract
inputs:
  max_results:
    type: integer
    description: "Max emails to return (1-100)"
    default: 20
    required: false
  
  from_filter:
    type: string
    description: "Filter by sender email"
    example: "boss@company.com"
    required: false
  
  label_filter:
    type: string
    enum: [INBOX, SENT, DRAFT, SPAM, TRASH]
    description: "Gmail label to filter by"
    required: false
  
  unread_only:
    type: boolean
    description: "Return only unread emails"
    default: false
    required: false

# Output contract
outputs:
  type: object
  properties:
    emails:
      type: array
      items:
        type: object
        properties:
          id:
            type: string
            description: "Gmail message ID (for read-message)"
          from:
            type: string
          subject:
            type: string
          preview:
            type: string
            description: "First 200 chars of email body"
          date:
            type: string
            format: iso8601
          labels:
            type: array
            items: string
          has_attachment:
            type: boolean
    total_count:
      type: integer
      description: "Total unfiltered email count in inbox"
    error:
      type: string
      description: "Error message if request failed"

# Quality & accuracy
quality:
  availability: "99.5%"             # uptime
  latency_p99_seconds: 5            # 99th percentile latency
  accuracy_notes: |
    - Respects Gmail filters and labels
    - Preview text is truncated (use Gmail/read-message for full body)
    - Date range queries not supported (use Gmail API directly)

# Dependencies & fallbacks
fallbacks:
  - id: Gmail/read-inbox-cached     # cached version for speed
    description: "Same output, but uses cached results (up to 5 min stale)"
    cost_reduction: "0.3×"

related_skills:
  - Gmail/read-message              # read full email body
  - Gmail/send-message              # send/reply to emails
  - Gmail/search                    # advanced search across Gmail
  - Gmail/archive-message           # move to archive
  - Gmail/add-label                 # tag with custom label

# Where it's used (presets/workflows)
used_in:
  - morning-ops/email-triage        # fetch emails for daily brief
  - outreach/email-validation       # check if sends succeeded

# Examples
examples:
  - name: "Get 10 most recent emails"
    inputs:
      max_results: 10
    output_snippet: |
      {
        "emails": [
          {
            "id": "msg_123abc",
            "from": "alice@company.com",
            "subject": "Q3 budget review",
            "preview": "Hi, can you review the attached budget spreadsheet...",
            "date": "2025-07-01T14:30:00Z",
            "labels": ["INBOX"],
            "has_attachment": true
          },
          ...
        ],
        "total_count": 47
      }
  
  - name: "Get unread emails from boss"
    inputs:
      from_filter: "boss@company.com"
      unread_only: true
    output_snippet: |
      {
        "emails": [
          { "from": "boss@company.com", "subject": "...", ... },
        ],
        "total_count": 3
      }

# Versioning & deprecation
version: "1.0"
deprecated: false
migration_notes: null

# Owner & support
maintained_by: "Anthropic Claude"
contact: "support@anthropic.com"
license: "Apache-2.0"

# Tags for discovery
tags:
  - email
  - gmail
  - read-only
  - communications
  - inbox-triage

# Metadata for filtering
metadata:
  required_scopes: ["gmail.readonly"]
  execution_mode: "synchronous"
  parallelizable: false            # don't call this 10× in parallel
  stateful: false                   # no side effects to track
  rate_limit: "60 calls/min"        # Gmail API limit
```

---

## Skill Registry & Discovery

### Directory Structure

```
skills/
├── _metadata.yaml                 # registry config
├── Gmail/
│   ├── read-inbox.yaml
│   ├── read-message.yaml
│   ├── send-message.yaml
│   └── ...
├── WebSearch/
│   ├── search.yaml
│   ├── search-news.yaml
│   └── ...
├── Trading/
│   ├── place-order.yaml
│   ├── backtest.yaml
│   └── ...
├── Research/
│   ├── decompose-query.yaml
│   ├── synthesize-findings.yaml
│   └── ...
└── Community/                     # external contributions
    ├── hermes/
    │   ├── email-classifier.yaml
    │   └── code-explainer.yaml
    └── openclaw/
        ├── competitor-monitor.yaml
        └── ...
```

### Registry Metadata

```yaml
# skills/_metadata.yaml
---
registry_version: "1.0"
last_updated: "2025-07-01T00:00:00Z"
total_skills: 62

categories:
  communications:
    skills: 8
    description: "Email, SMS, chat, messaging"
  
  web:
    skills: 12
    description: "Search, fetch, web scraping"
  
  trading:
    skills: 15
    description: "Orders, backtesting, risk management"
  
  research:
    skills: 10
    description: "Decomposition, synthesis, verification"
  
  content:
    skills: 9
    description: "Image, video, document generation"

featured:
  - Gmail/read-inbox              # most-used
  - WebSearch/search              # essential
  - Trading/place-order           # high-value

integrations:
  gmail:
    status: connected
    skills: 8
    scope: gmail.readonly + gmail.modify
  
  drive:
    status: connected
    skills: 6
    scope: drive

  alpaca:
    status: not_connected
    skills: 12
    message: "Run: donald mcp connect alpaca"
```

---

## CLI: Skill Discovery Commands

### Search

```bash
# Find all email skills
donald skills search email
# Output:
# Gmail/read-inbox        — Fetch emails from inbox
# Gmail/read-message      — Read full email body
# Gmail/send-message      — Send or reply to email
# Gmail/search            — Advanced search across Gmail
# Gmail/archive-message   — Move to archive

# Search by description
donald skills search "summarize emails"
# Output:
# Gmail/read-inbox        — Fetch and list emails...
# Gmail/summarize         — Summarize email thread

# Filter by category
donald skills search --category communications
# Output:
# Twilio/send-sms         — Send SMS message
# Twilio/send-voice       — Make voice call
# Gmail/read-inbox        — Fetch emails...
# ... (all 8 communication skills)

# Filter by cost
donald skills search --max-cost-usd 0.05
# Output:
# Gmail/read-inbox        ($0.01)
# WebSearch/search        ($0.02)
# Research/decompose      ($0.03)
# (skills costing ≤$0.05 per call)

# Filter by integration
donald skills search --requires gmail
# Output:
# (all 8 Gmail skills, with status: connected or not_connected)

# Filter by tags
donald skills search --tag read-only --tag fast
# Output:
# (skills marked as read-only AND fast)
```

### Inspect

```bash
# See full skill spec
donald skills show Gmail/read-inbox
# Output: (full YAML from above)

# See just the inputs/outputs
donald skills show Gmail/read-inbox --io
# Output:
# INPUTS:
#   max_results: integer (1-100, default 20)
#   from_filter: string (optional)
#   label_filter: [INBOX|SENT|DRAFT|SPAM|TRASH]
#   unread_only: boolean (default false)
#
# OUTPUTS:
#   emails: array of {id, from, subject, preview, date, labels, has_attachment}
#   total_count: integer
#   error: string (if failed)

# See what skills use this one
donald skills show Gmail/read-inbox --used-by
# Output:
# morning-ops/email-triage
# outreach/email-validation

# See recent performance
donald skills show Gmail/read-inbox --metrics
# Output:
# Calls (last 7 days): 142
# Avg latency: 2.1s (p99: 5.2s)
# Error rate: 0.7%
# Avg cost: $0.011 (estimated $0.01)
# Cache hit rate: 45% (results reused)
```

### Install

```bash
# Install a skill from community source (Hermes Agent library)
donald skills install hermes:email-classifier
# Output:
# ✓ Installed hermes:email-classifier (v1.2)
# Location: skills/Community/hermes/email-classifier.yaml
# Dependencies: Gmail/read-message (already available)
# Ready to use: donald skills show hermes:email-classifier

# Install from GitHub
donald skills install github:MelinaSimp/donald/skills/trading:custom-backtest
# Output:
# ✓ Installed custom-backtest (v0.1)
# Warning: This skill is not certified; use with caution
# Ready to use: donald skills show custom-backtest

# Install with a specific version
donald skills install hermes:arxiv@2.0
# (useful when skills evolve)

# List all installed (non-core) skills
donald skills list --custom
# Output:
# hermes:email-classifier       (v1.2, 3 calls, $0.15 total cost)
# custom-backtest               (v0.1, not used yet)
```

### Remove

```bash
# Uninstall a skill (cannot be used in new runs)
donald skills remove hermes:email-classifier
# Output:
# ✓ Removed hermes:email-classifier
# Existing presets using this skill: none
# Safe to remove
```

---

## Skill Usage in Presets

Presets reference skills by ID:

```yaml
# configs/presets/morning-ops.yaml
stages:
  - id: email-triage
    name: "Email Triage"
    skills:
      - Gmail/read-inbox          # skill ID
      - Gmail/summarize           # skill ID
      - Gmail/draft-reply         # skill ID
    model: claude-opus-4-8
```

When the preset runs, the executor:
1. Resolves skill IDs to specs (from `skills/`)
2. Checks if required integrations are connected
3. Calls skills in sequence/parallel
4. Logs cost + latency per skill call

---

## Skill Authoring Guide

### Minimal Skill (read-only, <100 tokens)

```yaml
# skills/WebSearch/search-news.yaml
id: WebSearch/search-news
name: "Search News"
description: "Find recent news articles matching a query"
provider: WebSearch
inputs:
  query:
    type: string
    required: true
outputs:
  articles:
    type: array
    items: object
examples:
  - inputs: {query: "SpaceX Starship"}
    output_snippet: "[{title: '...', url: '...', date: '...'}]"
tags: [news, search, read-only]
```

### Full Skill (complex, needs examples)

Use the Gmail/read-inbox template above as a reference. Include:
- Detailed description
- Input validation (types, enums, ranges)
- Output schema
- Cost estimates
- Fallbacks & related skills
- Multiple examples
- Quality metrics

### Adding a Custom Skill

```bash
# Create a new skill spec
cat > skills/Trading/kelly-fraction.yaml <<'EOF'
id: Trading/kelly-fraction
name: "Kelly Fraction Calculator"
description: "Calculate optimal position size using Kelly criterion"
provider: Trading
inputs:
  win_rate:
    type: number
    min: 0
    max: 1
    required: true
  avg_win_pct:
    type: number
    required: true
  avg_loss_pct:
    type: number
    required: true
  kelly_fraction:
    type: number
    default: 0.25
    description: "Fractional Kelly (usually 0.1-0.5 for safety)"
outputs:
  position_size_pct:
    type: number
    description: "Recommended % of portfolio per trade"
examples:
  - inputs: {win_rate: 0.55, avg_win_pct: 2, avg_loss_pct: 1.5}
    output_snippet: "{position_size_pct: 0.033}"
EOF

# Register it
donald skills register skills/Trading/kelly-fraction.yaml
# Output: ✓ Registered Trading/kelly-fraction
```

---

## Cost Model & Optimization

Every skill declares its cost:

```yaml
cost_estimate:
  tokens_per_call: 500
  usd_per_call: 0.01
  cache_friendly: true
```

The preset executor tracks actual costs:

```bash
donald metrics --preset morning-ops --breakdown skills
# Output:
# Stage: email-triage
#   Gmail/read-inbox         — 20 calls, $0.20 actual vs $0.20 est (perfect)
#   Gmail/summarize          — 1 call, $0.10 actual vs $0.15 est (30% cheaper)
#   Gmail/draft-reply        — 3 calls, $0.09 actual vs $0.06 est (50% over)
#
# Total: $0.39 actual vs $0.41 estimated
```

Then optimize:

```bash
donald skills optimize --preset morning-ops
# Output:
# Suggestions:
#   - Gmail/summarize uses claude-opus; could use claude-sonnet for 60% cost ↓
#   - Gmail/read-inbox results cache well; enable caching for 40% cost ↓
#
# Estimated savings: $0.12/run (30% reduction)
```

---

## Skill Marketplace (Future)

Eventually, users share skills:

```bash
# Publish your custom skill
donald skills publish skills/Trading/kelly-fraction.yaml --to hermes
# Output: ✓ Published to Hermes Agent library
# URL: https://hermes.ai/skills/kelly-fraction
# Users can now: donald skills install hermes:kelly-fraction

# Browse marketplace
donald skills browse --marketplace hermes --sort stars
# Output:
# ⭐⭐⭐⭐⭐ email-classifier       (456 installs)
# ⭐⭐⭐⭐  competitor-monitor     (123 installs)
# ⭐⭐⭐   podcast-summarizer     (45 installs)
```

---

## Integration with Audit Log

Every skill call is logged:

```json
{
  "timestamp": "2025-07-01T14:30:00Z",
  "preset_id": "morning-ops",
  "stage_id": "email-triage",
  "skill_id": "Gmail/read-inbox",
  "inputs": {"max_results": 20, "unread_only": false},
  "outputs": {"emails": [...], "total_count": 47},
  "duration_seconds": 2.1,
  "tokens_input": 150,
  "tokens_output": 350,
  "cost_usd": 0.011,
  "cache_hit": false,
  "error": null
}
```

Query across skill usage:

```bash
# Which skills are most expensive?
donald skills stats --sort cost
# Output:
# Trading/backtest          — $0.50/call (12 calls/month = $6)
# Research/adversarial-verify — $0.30/call (8 calls/month = $2.40)
# WebSearch/search          — $0.02/call (200 calls/month = $4)

# Which skills are most reliable?
donald skills stats --sort reliability
# Output:
# Gmail/read-inbox         — 99.9% uptime (1 error in 1000 calls)
# WebSearch/search         — 98.5% uptime
# Trading/place-order      — 100% uptime (critical skill)
```

---

## Implementation Roadmap

### Phase 1 (Week 1)
- [ ] Define skill spec schema (JSON Schema)
- [ ] Write 10 core skills (Gmail, WebSearch, Trading, Research)
- [ ] Implement PresetExecutor to load + call skills
- [ ] Add `donald skills show` command

### Phase 2 (Week 2)
- [ ] Add skill discovery commands (`search`, `list`, `show --io`, `--metrics`)
- [ ] Implement audit logging per skill
- [ ] Add `donald skills install` from GitHub
- [ ] Cost tracking per skill

### Phase 3 (Week 3)
- [ ] Skill optimization suggestions (cache, model downgrade, etc.)
- [ ] Fallback chains (if Gmail fails, queue locally)
- [ ] `donald skills verify` (validate spec, test inputs/outputs)

### Phase 4+ (Future)
- [ ] Community marketplace (Hermes, OpenClaw)
- [ ] Skill versioning & deprecation
- [ ] ML-based skill recommendations ("for your use case, try X")

---

## See Also

- [Presets README](./presets/README.md) — How skills are used
- [IMPLEMENTATION_GUIDE](./presets/IMPLEMENTATION_GUIDE.md) — Executor details
- [agentskills.io](https://agentskills.io/) — Open standard reference
