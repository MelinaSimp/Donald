# Wren — agent spec

> Single source of truth for what we're building and why. Written from the Tier 0
> interview. Edit this file when intentions change; the rest of the build reads
> from it.

## Identity

- **Name:** Wren
- **One-line purpose:** A personal, voice-first AI assistant that remembers me and
  can act on my behalf.
- **For:** Just me (single user). Per-user state is kept in mind so it *could*
  grow to a small team later, but nothing in the harness assumes more than one
  person today.
- **Personality / tone (text):** Warm, plain-spoken, and brief. Wren answers
  directly, skips preamble, and doesn't pad. The *spoken* character (Tier 3) comes
  from the chosen ElevenLabs voice; this text personality keeps the brain
  consistent everywhere.

## First three capabilities (first tools + first test cases)

1. **Reminders & to-dos** — capture, list, complete. (`add_reminder`, `list_reminders`, `complete_reminder`)
2. **Q&A over my notes** — search and read my notes. (`search_notes`, `read_note`)
3. **Web lookups** — quick facts, weather, light research. (`web_search`)

A fourth capability from the interview — **drafting messages** — is built as the
Tier 6 *gated* example, because sending is on the "never without asking" list.
`draft_message` (write a draft, safe) is separate from `send_message` (gated).

## Stack & model

- **Language / runtime:** Python 3.11+ — boring, well-supported, good audio + HTTP
  + Anthropic SDK libraries.
- **Model provider:** Anthropic, official `anthropic` SDK, behind a thin seam
  (`wren/llm.py`) so it can be swapped without touching the rest of the harness.
- **Default model:** `claude-opus-4-8`. For lower voice latency you can switch to
  `claude-sonnet-4-6` or `claude-haiku-4-5` in `config.yaml` — one-line change, no
  code edit.
- **Runs:** Laptop-first. The heartbeat (Tier 5) is a separate loop designed to
  relocate to an always-on host later without a rewrite.

## Voice & boundaries

- **How I talk to it:** Text first (always kept alive as the debug + fallback
  path), then push-to-talk in Tier 3. Wake word is a later step.
- **Ears:** Deepgram (speech-to-text), behind `wren/voice/stt.py`.
- **Mouth:** ElevenLabs (text-to-speech), behind `wren/voice/tts.py`. The voice id
  lives in `config.yaml`, not in code.
- **Never without asking (hard confirmation gate, Tier 6):**
  1. Send messages (email / text / DM)
  2. Spend money (any purchase or payment)
  3. Delete data (files, notes, records)
  4. Change settings (system/account settings, or Wren's own config)
- **Proactive:** Yes — but **quiet by default**. Wren earns the right to interrupt;
  most checks produce nothing most of the time. Built in Tier 5.

## Secrets

API keys live in environment variables / `.env` (git-ignored). Never in source.
Required: `ANTHROPIC_API_KEY`. For voice: `DEEPGRAM_API_KEY`, `ELEVENLABS_API_KEY`.

## The five parts (architecture)

- **Brain** — `wren/agent.py` + `wren/llm.py`: one conversation loop, one entry
  point, used by text, voice, and the heartbeat alike.
- **Hands** — `wren/tools/`: a registry of typed, described tools. Adding a
  capability means adding one tool, never editing the loop.
- **Ears & mouth** — `wren/voice/`: STT/TTS/audio wrapped around the *same* brain.
- **Memory** — `wren/memory.py` + `data/memory.json`: durable, human-readable facts
  loaded at the start of every conversation.
- **Heartbeat** — `wren/heartbeat.py`: background loop for scheduled checks and
  proactive (quiet) surfacing.
- **Rails** — `wren/safety.py`: confirmation gate, audit log, kill switch; config
  in `config.yaml`.

The discipline: **one shared agent core, many ways in and out.** If the agent
logic is ever written twice, stop and unify it.
