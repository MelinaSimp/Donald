# Agent Scoping Matrix — DONALD

**Status:** Active (V2026.6.11)  
**Framework:** OpenClaw  
**Last Updated:** 2026-07-02

---

## System Profile

### Identity

| Property | Value |
|----------|-------|
| **Name** | DONALD (Distributed Open Network Agent with Localized Determination) |
| **Type** | Personal Jarvis-style Terminal Agent |
| **Provider** | Anthropic (`claude-opus-4-8`) |
| **Running Context** | Local terminal, single user |
| **Memory Layer** | Persistent (`~/.donald/memory.md`) |

### Design Principles

> **Least Privilege.** Every agent holds exactly the tools its job requires and not one more.
> 
> **Bound Everything.** Every loop has a max iteration count, every call a token ceiling, every agent a declared model.
> 
> **Humans Decide.** Approval gates on mutations; Donald proposes, the user disposes.

---

## Tool Matrix

### Tier 1: Safe Reads

| Tool | Policy | Fallback | Notes |
|------|--------|----------|-------|
| `web_search` | **Auto** | Return empty results | Rate-limited, no auth required |
| `read_file` | **Auto** | Reject + explain | Sandboxed to CWD; `..` and `/` blocked |
| `vision` | **Auto** | Return "unable to analyze" | Image inspection only, no generation |

**Execution:** Immediate. No approval gate.

---

### Tier 2: Mutating Operations

| Tool | Policy | Threshold | Fallback |
|-------|--------|-----------|----------|
| `write_file` | **Asks first** | Show exact content | Decline → adapt strategy |
| `edit_file` | **Asks first** | Show diff/context | Decline → suggest alternative |
| `run_shell` | **Asks first**¹ | Show command | Decline → replan |
| `remember` | **Auto** | Your notes only | Saved to `memory.md` |

¹ Skipped if command matches `shell_auto_approve` (default: `['git status', 'ls', 'cat']`).

**Execution:** Waits for user confirmation (`y`/`n`). Decline is handled gracefully.

---

### Tier 3: Blocked Operations

| Pattern | Reason | Override |
|---------|--------|----------|
| `rm -rf` | Destructive | Manual review required |
| `sudo reboot` | System-level | Not available |
| `chmod 000` | Permission lock | Manual review |

**Execution:** Rejected immediately with explanation. No fallback.

---

## Thinking & Memory Profiles

### Thinking Configuration

```yaml
thinking: high
  depth: "complex reasoning for multi-step tasks"
  max_tokens: 8000
  temperature: 0.7 (low randomness)
```

**When to use:**
- Multi-step tool chains (read → analyze → edit → verify)
- Complex file edits with interdependencies
- Web research requiring synthesis

### Memory Layout

```
~/.donald/
├── memory.md              # Long-term facts (user prefs, context)
├── memory.bak             # Backup (before /update_memory)
└── config.json            # Settings (persistent across sessions)
```

**Memory Curation:**
- **Add:** `remember <fact>` — appended to memory
- **Update:** `/update_memory` — rewrite whole memory set (backs up old)
- **View:** `/memory` — show current facts
- **Wipe:** `/forget` — delete memory.md

> Memory is **curated, not just appended**. A long memory becomes noise. Use `/update_memory` to trim, prioritize, and reorganize durable facts.

---

## Execution Bounds

### Per-Call Limits

| Limit | Value | Reason |
|-------|-------|--------|
| **Max tokens** | 4,096 | Avoid runaway output |
| **Max iterations** | 10 | Bound tool loops |
| **Shell timeout** | 60s | Prevent hanging |
| **Max output chars** | 100,000 | Memory/display |

Override in `config.json`:

```json
{
  "max_tokens": 8000,
  "shell_timeout_s": 120,
  "max_output_chars": 200000
}
```

### Tool Frequency Caps

| Tool | Cap | Window | Action |
|------|-----|--------|--------|
| `web_search` | 10/session | Rolling | Warn, then skip |
| `run_shell` | 20/session | Rolling | Warn, then require confirmation |
| `write_file` | 15/session | Rolling | Warn, then require confirmation |

---

## Approval Gate Logic

### Smart Mode (Default)

```
User asks: "delete that file"
↓
Donald recognizes destructive intent
↓
Shows exact action: "remove /path/to/file"
↓
Waits for approval (y/n)
↓
User declines
↓
Donald adapts: "I'll archive it instead" → proposes alternative
```

### Manual Mode

```
User sets: "approval_mode: manual"
↓
All tool calls require explicit "y" approval
↓
No intelligent fallbacks
↓
Useful for high-security environments
```

### Hardline Mode

```
User sets: "approval_mode: hardline"
↓
Destructive patterns (rm, reboot, etc.) are blocked
↓
No human override
↓
Useful for untrusted environments
```

Configure in `config.json`:

```json
{
  "approval_mode": "smart"
}
```

---

## Fallback Thresholds

### Tool Failures

| Failure | Response |
|---------|----------|
| **Web search fails** | Return empty results; continue with offline knowledge |
| **File read blocked** | Explain sandboxing; suggest alternative path |
| **Shell timeout** | Kill process; report timeout; ask to simplify |
| **User declines approval** | Acknowledge; propose alternative approach |

---

## Integration Points

### CLI Entry

```bash
donald              # Start interactive session
```

### Commands (In-Session)

| Command | Scoped To | Effect |
|---------|-----------|--------|
| `/help` | Any | Show command list |
| `/reset` | Any | Clear conversation, start fresh |
| `/memory` | Any | Show what Donald remembers |
| `/forget` | Secure | Wipe long-term memory |
| `/voice` | Voice-enabled | Toggle spoken replies |
| `/listen` | Voice-enabled | Speak next message |
| `/exit` | Any | Quit |

---

## Configuration Reference

### `~/.donald/config.json`

```json
{
  "model": "claude-opus-4-8",
  "max_tokens": 4096,
  "shell_timeout_s": 60,
  "max_output_chars": 100000,
  "shell_auto_approve": ["git status", "git log", "ls", "cat", "pwd"],
  "approval_mode": "smart",
  "voice": false
}
```

### Environment Variable Overrides

All config keys can be overridden via env vars with `DONALD_` prefix (uppercase):

```bash
export DONALD_MODEL=claude-opus-4-8
export DONALD_MAX_TOKENS=8000
export DONALD_SHELL_TIMEOUT=120
export DONALD_APPROVAL_MODE=manual
```

---

## Decision Matrix

### When to Approve Approval (meta)

| Scenario | Decision | Rationale |
|----------|----------|-----------|
| User says "run git status" | **Auto** | Read-only, allowlisted |
| User says "delete old logs" | **Prompt** | Destructive but recoverable |
| User says "remove system files" | **Block** | Dangerous + not in CWD |
| User says "search for X" | **Auto** | Web search, no local impact |
| User says "create new file" | **Prompt** | Mutating filesystem |

### Thinking Profiles by Task

| Task | Thinking | Reasoning |
|------|----------|-----------|
| Summarize a file | `low` | Straightforward read + compress |
| Multi-step edit chain | **high** | Interdependencies, verify between steps |
| Bug diagnosis | **high** | Reason about symptoms + traces |
| Web research synthesis | **high** | Integrate multiple sources |
| One-liner command | `low` | No ambiguity |

---

## Testing & Verification

### Pre-Deployment Checklist

- [ ] Approval gates trigger on all mutations
- [ ] Sandbox correctly blocks `..` and absolute paths
- [ ] Memory persistence works across sessions
- [ ] Tool frequency caps enforce limits
- [ ] Fallback paths gracefully handle failures
- [ ] All commands accept stdin/argv (headless mode)

### Test Coverage

```bash
pytest -v
# Run with coverage:
pytest --cov=donald
```

---

## Future Expansions (Planned)

| Tier | Feature | Status |
|------|---------|--------|
| 2 | Discord/Slack pairing | Planned |
| 3 | Config hot-reload | Planned |
| 4 | Multi-user mode | Planned |
| 5 | Custom tool plugins | Research |

---

**Questions?** See [README.md](./README.md) or open an [issue](https://github.com/MelinaSimp/Donald/issues).
