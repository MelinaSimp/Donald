# Donald

A personal, Jarvis-style assistant you build and own — text first, then voice,
then memory, then proactive. Each tier runs on its own and is verified before
the next begins.

```
Tier 0  text conversation loop      ✅ built & verified
Tier 1  tool registry + 12 tools    ✅ built & verified
Tier 2  voice (Deepgram + 11Labs)   ✅ built (needs your keys to run)
Tier 3  persistent memory (SQLite)  ✅ built & verified
Tier 4  proactive background loop   ✅ built & verified
Tier 5  safety rails                ✅ built & verified
```

## Quick start

```bash
pip install -e .                 # core (text, tools, memory, safety)
cp .env.example .env             # then add your ANTHROPIC_API_KEY
donald                           # text chat
```

No key yet? Donald drops to an offline **mock brain** so you can still drive the
whole loop (including tools) before spending a token.

### Commands

```bash
donald            # Tier 0/1/3/5 — text conversation loop
donald voice      # Tier 2 — talk with your voice
donald daemon     # Tier 4 — proactive loop on; Donald can reach out first
donald tools      # list Donald's tools
donald doctor     # show which tiers are configured and ready
```

In a chat, `/tools`, `/history`, `/reset`, `/quit` are available.

## The tiers

**Tier 0 — text loop** (`donald/conversation.py`, `donald/agent.py`). A plain
REPL over an `Agent` that drives the brain ⇄ tool cycle. Debuggable with no
audio and no API key (mock brain).

**Tier 1 — tools** (`donald/tools/`). A registry; add a capability by writing a
module with `register(reg)`. Shipped: `get_time`, `set_reminder`,
`list_reminders`, `web_search`, `read_file`, `list_dir`, `write_file`,
`run_shell`, `remember`, `recall`, `list_memories`, `forget`.

**Tier 2 — voice** (`donald/voice/`). Deepgram for speech-to-text, ElevenLabs
for speech-out, over the same agent. `pip install -e ".[voice]"` and set the
keys.

**Tier 3 — memory** (`donald/memory.py`). One SQLite file holding facts,
reminders and an optional transcript. Survives restarts; remembered facts are
injected into the system prompt each session.

**Tier 4 — proactive loop** (`donald/proactive.py`, `donald/daemon.py`). A
background loop that checks for due reminders and other triggers and reaches out
first. Off by default (`DONALD_PROACTIVE=off`).

**Tier 5 — safety** (`donald/safety.py`). A gate on every tool: hard-blocks
dangerous shell commands, requires confirmation for world-changing tools, and —
crucially — **denies mutating actions while running unattended** so the
proactive loop can't change your world without you. Everything is audit-logged.

## Verify

```bash
pytest                  # headless tiers: text, tools, memory, safety
donald doctor           # readiness of every tier
```
