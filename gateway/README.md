# Donald Gateway — the connective tissue

This package is the backend "brain stem" of the Donald (a.k.a. Jarvis) system.
You build the UI in Claude design; the UI talks to **this gateway**, and the
gateway ties three things into one connected system:

```
                 ┌──────────────────────────┐
  Your UI  ──────▶   DONALD GATEWAY (this)   │
 (Claude design)│   REST + WebSocket         │
                 │                            │
                 │   ┌────────────────────┐   │
                 │   │  Donald brain      │   │  Claude Opus 4.8 +
                 │   │  (donald/ persona) │   │  drift-proof voice layers
                 │   └─────────┬──────────┘   │
                 │             │ hermes_execute (a tool)
                 │   ┌─────────▼──────────┐   │
                 │   │  Hermes connector  │───┼──▶  Hermes on YOUR computer
                 │   │  (OpenAI-compat)   │   │     :8642  terminal/files/web/skills
                 │   └────────────────────┘   │
                 │   ┌────────────────────┐   │
                 │   │  Voice (ElevenLabs)│───┼──▶  Trump-style TTS
                 │   └────────────────────┘   │
                 └──────────────────────────┘
```

**Donald is the voice and the decision-maker.** When a request needs real
action on your machine, Donald delegates to **Hermes** via one tool,
`hermes_execute`. Hermes (running locally, with terminal/file/web/skill access)
does the work and returns a result; Donald narrates and decides what's next.
ElevenLabs turns Donald's reply into speech.

## How the pieces connect

| Piece | What it is | How the gateway reaches it |
|-------|------------|----------------------------|
| **Donald brain** | The cocky Claude personality in `donald/` | Anthropic API (`ANTHROPIC_API_KEY`) |
| **Hermes** | The local NousResearch agent on your computer | Its OpenAI-compatible API server at `http://127.0.0.1:8642` (`/v1/chat/completions`, `Authorization: Bearer <API_SERVER_KEY>`) |
| **Voice** | ElevenLabs text-to-speech | `https://api.elevenlabs.io` (`ELEVENLABS_API_KEY` + a `ELEVENLABS_VOICE_ID`) |

### One-time Hermes setup (on your machine)

Hermes is installed and run on **your** computer (not in this repo). Turn on its
API server in `~/.hermes/.env`:

```
API_SERVER_ENABLED=true
API_SERVER_HOST=127.0.0.1
API_SERVER_PORT=8642
API_SERVER_KEY=change-me-local-dev
```

Restart Hermes, then put the same key in the gateway's `HERMES_API_KEY`.

## Run

```bash
pip install -r requirements.txt
cp gateway/.env.example gateway/.env      # fill in keys
set -a; source gateway/.env; set +a       # load them into the env
python -m gateway.server                  # serves on 127.0.0.1:8765
```

Check it's alive (and whether Hermes is reachable):

```bash
curl localhost:8765/health
```

## What the UI sends and receives

**One-shot (REST):**

```
POST /api/chat   {"session_id": "abc", "message": "what's in my downloads folder?"}
→ {"text": "...", "events": [ ... ]}
```

**Streaming (WebSocket `/ws`)** — send:

```json
{ "type": "chat", "session_id": "abc", "message": "summarize my latest email" }
```

…and receive a stream of events:

| event | meaning |
|-------|---------|
| `delta` | a chunk of Donald's spoken text |
| `tool_call` | Donald is delegating to Hermes (`task`, `reason`) |
| `tool_result` | Hermes came back (`flagged`, `flag_reasons`, `preview`) |
| `voice` | base64 MP3 of Donald's reply (`audio_b64`, `mime`) |
| `final` | the finished reply text |
| `error` | something went wrong |

**Ad-hoc speech:** `POST /api/voice {"text": "..."}` → `audio/mpeg`.

## Security (wired from this repo's own `security/` library)

- **Untrusted Hermes output** is passed through `security.injection_gate.gate`
  and handed to the model inside an `<untrusted_hermes>` envelope — data, never
  instructions. Injection attempts surface as `flagged: true` on `tool_result`.
- **All logs** go through `security.log_redact.redact`, so keys/PII never reach
  a log sink.
- **Optional approval gate:** the orchestrator accepts a `confirm_cb` hook;
  wire it to a UI confirm dialog to require sign-off before Hermes does anything
  irreversible. (Off by default for a smooth local dev loop.)

## Layout

| File | Role |
|------|------|
| `config.py` | Env-driven `Settings` |
| `connectors/base.py` | `AgentConnector` protocol — the adapter seam |
| `connectors/hermes.py` | Hermes OpenAI-compatible connector |
| `connectors/voice.py` | ElevenLabs TTS connector |
| `orchestrator.py` | Donald's turn loop: brain + Hermes-as-tool + security gates + voice |
| `server.py` | FastAPI REST + WebSocket the UI talks to |

## Swapping Hermes out

The orchestrator only depends on the `AgentConnector` protocol
(`connectors/base.py`). To point Donald at a different local agent, write a new
class with `name`, `health()`, `execute()`, and `aclose()`, and pass it in —
nothing else changes.
