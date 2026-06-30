# Donald — Voice-First Mobile PWA Agent

A hands-free, voice-driven mobile companion for an AI agent. Tap an animated orb, speak your request, and get a natural spoken response. Built for iOS PWA with battle-tested audio architecture.

## Features

- **Voice-first**: Tap the orb, talk hands-free, listen to responses
- **Animated orb**: WebGL scene responsive to voice (analyser-driven)
- **Claude Sonnet 4.6**: Conversational AI with streaming responses
- **Tools**: Weather, Calendar (read/create/modify), Email (read/send)
- **Confirmation gate**: Risky actions (email, calendar changes) require voice confirmation
- **iOS-optimized**: All 9 critical iOS Safari quirks baked in (MP3 streaming, dual-path audio, silent-switch routing, etc.)
- **SQLite persistence**: Conversation history survives restarts
- **HTTPS + WSS**: Secure, auto-provisioned with Caddy

## Architecture

```
iPhone PWA (HTTPS + WSS)
    ↓ Caddy (auto Let's Encrypt, reverse proxy)
    ↓
FastAPI server (bearer-token auth)
    ├─ Deepgram (STT streaming)
    ├─ Claude Sonnet 4.6 (conversation, tools)
    └─ ElevenLabs (TTS → MP3 streaming)
    ↓
SQLite (conversation history)
```

## Quick Start — Development

```bash
# Clone repo
git clone https://github.com/yourusername/donald.git && cd donald

# Install dependencies
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Create .env (see .env.example)
cp .env.example .env
# Edit .env with your API keys

# Initialize database
python3 -c "from server.db import init_db; init_db()"

# Run server
python3 -m uvicorn server.main:app --reload

# In another terminal, run tests
pip install -r requirements-dev.txt
pytest tests/ -v
```

Open `http://localhost:8000` in a browser. (Note: voice features require HTTPS in production.)

## Deployment

See [DEPLOYMENT.md](./DEPLOYMENT.md) for full production setup with Caddy, systemd, and iOS PWA install.

## Project Structure

```
├── server/
│   ├── main.py           # FastAPI app, WebSocket, TTS endpoint
│   ├── auth.py           # Bearer token auth (3 paths)
│   ├── config.py         # Environment variable config
│   ├── db.py             # SQLite conversation store, TTS cache
│   ├── brain.py          # Claude Sonnet loop, tools
│   ├── deepgram.py       # Deepgram STT streaming (stub)
│   └── elevenlabs.py     # ElevenLabs TTS → MP3
├── frontend/
│   ├── index.html        # PWA shell (no-cache, iOS meta tags)
│   ├── scene.js          # Three.js orb + voice reactivity
│   ├── voice.js          # WebSocket, mic capture, dual-path audio
│   ├── sw.js             # Service worker (pass-through)
│   └── manifest.webmanifest
├── tests/
│   ├── test_auth.py      # Auth token extraction & validation
│   └── test_db.py        # Database, TTS cache (non-evicting), TTL
├── requirements.txt      # Python dependencies
├── requirements-dev.txt  # pytest, httpx
├── .env.example          # Config template
└── DEPLOYMENT.md         # Production setup
```

## iOS Quirks Baked In

1. **MP3 over wire**, not raw PCM — iOS WebAudio + raw is fragile
2. **Dual-path audio** — `<audio>` for sound + `BufferSource` for analyser data (iOS Safari bug: MediaElementSource analyser returns zeros)
3. **Silent switch routing** — `<audio>` element respects silent switch; WebAudio destination doesn't
4. **Synchronous `play()`** — Must call within click handler; `await fetch()` revokes gesture window
5. **Non-evicting TTS** — iOS makes two GET requests; cache by TTL, not on-read
6. **Token auth** — Supports 3 paths (header, custom header, query param) since `<audio>` and WS can't set custom headers
7. **No-store caching** — Shell HTML cached by PWA can strand users on broken versions
8. **100dvh viewport** — `100vh` doesn't extend under home indicator on iOS PWA
9. **AudioContext re-suspension** — Backgrounding/lock screen suspends it; resume on every gesture

## Tools

### Weather (read-only)
- `get_weather(location, units)` → current conditions + forecast
- No confirmation needed

### Calendar (read + gated writes)
- `list_calendar_events(days_ahead)` → upcoming events
- `create_calendar_event(title, start_time, end_time, description)` → gated behind `await_confirmation`
- `update_calendar_event(event_id, title, start_time, end_time)` → gated

### Email (read + gated send)
- `list_emails(query, limit)` → search inbox
- `send_email(to, subject, body)` → gated behind `await_confirmation`

### Confirmation Gate
- Call `await_confirmation` before risky tools; voice proposal, wait for user "yes/no"
- System prompt enforces this via a hard rule
- PWA displays amber confirmation chip until user confirms or cancels

## Anti-Hallucination Rule

Numbers about real-world data (weather, calendar times, email counts, etc.) **must come from a tool called this turn**. No fabrication, rounding, or estimation from training data.

## Testing

```bash
pytest tests/ -v
# 14 tests covering auth, database, TTS cache, non-eviction, TTL
```

## API Keys

Get these free (or cheap):

- **Anthropic Claude**: https://console.anthropic.com (free tier: 50k tokens/month)
- **Deepgram STT**: https://console.deepgram.com (free: 1000 minutes/month)
- **ElevenLabs TTS**: https://elevenlabs.io (free: 10k characters/month)
- **Google Calendar + Gmail**: Create a project at https://console.cloud.google.com (free tier)

## Environment Variables

See `.env.example`:

```bash
BEARER_TOKEN=your-secret-token
ANTHROPIC_API_KEY=sk-ant-...
DEEPGRAM_API_KEY=...
ELEVENLABS_API_KEY=sk_...
HOST=0.0.0.0
PORT=8000
DEBUG=false
DB_PATH=donald.db
TTS_CACHE_TTL_SECONDS=300
```

## Browser Compatibility

- **iOS Safari 15+** (PWA install, WebSocket, getUserMedia, WebAudio all required)
- **Chrome/Chromium** (desktop dev only; PWA install not tested)
- **Other browsers**: Untested, not recommended

## License

MIT

## Contributing

PRs welcome. Focus on iOS compatibility when making audio/PWA changes — test on a real iPhone.

---

Built with [Claude](https://claude.ai), [Three.js](https://threejs.org), [FastAPI](https://fastapi.tiangolo.com), [Deepgram](https://deepgram.com), [ElevenLabs](https://elevenlabs.io).
