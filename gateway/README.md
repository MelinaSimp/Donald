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
| **Donald brain** | The cocky personality in `donald/` | `DONALD_PROVIDER=anthropic` → Claude (`ANTHROPIC_API_KEY`); or `DONALD_PROVIDER=openai` → any OpenAI-compatible API (MiniMax/groq/vLLM) via `DONALD_BASE_URL` + `DONALD_API_KEY` + `DONALD_MODEL` |
| **Hermes** | The local NousResearch agent on your computer | Its OpenAI-compatible API server at `http://127.0.0.1:8642` (`/v1/chat/completions`, `Authorization: Bearer <API_SERVER_KEY>`) |
| **Voice** | ElevenLabs text-to-speech | `https://api.elevenlabs.io` (`ELEVENLABS_API_KEY` + a `ELEVENLABS_VOICE_ID`) |

### Reaching Hermes: two modes (`HERMES_MODE`)

Hermes runs on **your** machine/server (not in this repo). Depending on how
it's packaged, pick one of:

**`HERMES_MODE=cli` (recommended for the Dockerised NousResearch stack).**
Donald drives Hermes' one-shot CLI — `hermes -z "<task>" --yolo` — which runs
the full agent (all tools, on the local model) and prints the answer. If Hermes
is in a container, the gateway reaches it with `docker exec`, so **run the
gateway on the same host** (it needs Docker access). Configure:

```
HERMES_MODE=cli
HERMES_DOCKER_CONTAINER=hermes-workspace-rzuj-hermes-agent-1  # docker ps; blank if not containerised
HERMES_CLI_PATH=/opt/hermes/.venv/bin/hermes
HERMES_MODEL=hermes            # "hermes" = use the container's configured default model
HERMES_TIMEOUT_S=300           # local models cold-load slowly
```

First make sure Hermes can actually answer (its model must be installed):

```
docker exec <container> ollama-or-hermes ...           # set model.default to an installed model
docker exec <container> /opt/hermes/.venv/bin/hermes -z "Reply OK" --yolo
```

**`HERMES_MODE=http`.** For a Hermes build that exposes an OpenAI-compatible
API server. Point `HERMES_BASE_URL`/`HERMES_API_KEY` at it (`/v1/chat/completions`).

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
| `final` | the finished reply text, plus a `grounding` annotation (see below) |
| `error` | something went wrong |

### Grounding annotation on `final`

Every `final` event carries a `grounding` object — the anti-hallucination
guardrail (north-star: *"never answer without a citation"*). It scores the reply
against the turn's tool trace and validates any inline citation markers
(`[v1]`, `[mem:…]`, `[reg:N]`, `[ss:N]`):

```jsonc
"grounding": {
  "score": 0.4,                // 0..1 composite
  "tier": "partial",           // "strong" | "partial" | "none"
  "summary": "Partially grounded — some claims uncited or unverified.",
  "parts": { "citation_count": 1, "retrieval_tools_called": 0, ... },
  "citations": { "overall": "invalid", "counts": {...}, "checks": [...] }
}
```

A fabricated citation (marker with no backing tool call) is flagged `missing`
and drags the verdict to `invalid` — so the UI can surface "not verified"
instead of trusting an unsourced answer. The check is trace-only by default
(dependency-free); back it with a `CitationContextProvider` (e.g. Donald's
Vault) to verify quotes and pages against real documents. See
`gateway/grounding/`.

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
| `orchestrator.py` | Donald's turn loop: brain + Hermes-as-tool + security gates + voice + grounding |
| `server.py` | FastAPI REST + WebSocket the UI talks to |
| `grounding/` | Citation grounding guardrail (ported from Drift's `lib/dante`): parse + verify citation markers, score how grounded each answer is |

## Swapping Hermes out

The orchestrator only depends on the `AgentConnector` protocol
(`connectors/base.py`). To point Donald at a different local agent, write a new
class with `name`, `health()`, `execute()`, and `aclose()`, and pass it in —
nothing else changes.
