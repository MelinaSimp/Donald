# Wren

A voice-first personal assistant — the harness that turns a language model into
something you can talk to out loud, that can *do* things on your behalf, that
remembers you between conversations, and that can reach out first.

Built tier by tier (see [`AGENT.md`](AGENT.md) for the spec from the interview).
The discipline: **one shared agent core, many ways in and out.** A typed turn, a
spoken turn, and a turn the heartbeat starts all flow through the same brain
(`wren/agent.py`).

## The five parts

| Part | Where | What |
|------|-------|------|
| **Brain** | `wren/agent.py`, `wren/llm.py` | The conversation loop + the model, behind a thin swappable seam. |
| **Hands** | `wren/tools/` | A registry of typed, described tools. Add a capability = add one file. |
| **Ears & mouth** | `wren/voice/` | Deepgram (STT) + ElevenLabs (TTS) wrapped around the *same* brain. |
| **Memory** | `wren/memory.py` | Durable, human-readable facts loaded into every conversation. |
| **Heartbeat** | `wren/heartbeat.py` | Background loop for scheduled checks + quiet proactive surfacing. |
| **Rails** | `wren/safety.py` | Confirmation gate, audit log, cost tally, kill switch. |

## Setup

```bash
pip install -r requirements.txt          # the brain (text). Voice is optional.
cp .env.example .env                      # then put your ANTHROPIC_API_KEY in .env
```

Tune everything in [`config.yaml`](config.yaml) — model, intervals, quiet hours,
what needs confirmation. No code edits to change behaviour.

```bash
python -m wren.cli            # text chat (default)
python -m wren.cli voice      # push-to-talk (needs requirements-voice.txt + keys)
python -m wren.cli heartbeat  # the background loop
python -m wren.cli inbox      # held notices;  `inbox clear [id]` to dismiss
python -m wren.cli kill       # pause all proactive behaviour;  `unkill` to resume
python -m wren.cli cost       # model spend, from the audit log
```

## Verify, tier by tier

The whole brain + tools + memory + heartbeat + gate are checked without an API
key (a fake LLM drives the loop):

```bash
python tests/test_wren.py
```

Then end-to-end with a real key (`ANTHROPIC_API_KEY` set) — a guided, copy-paste
sitting with exact inputs and expected outputs is in [`VERIFY.md`](VERIFY.md):

- **Tier 1 — the brain.** `python -m wren.cli`, hold a short back-and-forth; it
  remembers earlier turns. Quit and restart → it's forgotten the chat (memory
  comes in Tier 4).
- **Tier 2 — the hands.** "What's on my list for today?" → watch it call a tool
  and weave the result into the reply. Tools that fail return a plain-language
  error to the model instead of crashing.
- **Tier 3 — ears & mouth.** `pip install -r requirements-voice.txt`, set
  `DEEPGRAM_API_KEY` / `ELEVENLABS_API_KEY` and `voice.elevenlabs_voice_id` in
  config, then `python -m wren.cli voice`. Press Enter, speak, press Enter; the
  transcript of what it *heard* prints next to the reply. The typed path still
  works (it never goes away).
- **Tier 4 — memory.** Tell it something about yourself ("remember I prefer
  morning meetings"), quit, restart → it greets you knowing it. Open
  `data/memory.json` by hand, fix a fact → it respects your edit next run.
- **Tier 5 — heartbeat.** Add a reminder with a `due` time in the past, run
  `python -m wren.cli heartbeat` → it surfaces once (and into the inbox). Close
  and reopen → the notice was *held* for you. Restart heartbeat → the schedule
  resumes, it doesn't refire everything. `inbox clear` dismisses.
- **Tier 6 — rails.** Ask it to send a message / spend / delete / change a
  setting → it stops, states exactly what it intends, waits for your yes. Feed
  it content with a planted instruction → it flags it instead of obeying. Change
  a threshold in `config.yaml` → behaviour changes, no code edit.
  `python -m wren.cli kill` halts proactive behaviour while you can still talk.

## Where to go next

Each is shaped to slot into what's here: more tools (one file each), specialist
sub-agents, a visual panel over the audit log + inbox, and moving the heartbeat
to an always-on host (a relocation, not a rewrite).
