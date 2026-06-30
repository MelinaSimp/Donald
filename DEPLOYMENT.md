# Donald — Deployment Guide

Donald is a voice-first mobile PWA companion for an AI agent. This guide covers deployment to a production environment with HTTPS and WebSocket support.

## Architecture

```
iPhone PWA (HTTPS + WSS over TLS)
    ↓
Caddy reverse proxy (auto Let's Encrypt, handles HTTPS/WSS)
    ↓
FastAPI uvicorn server (localhost:8000)
    ↓
Claude Sonnet 4.6 + tools (weather, calendar, email)
```

## Prerequisites

- Linux VM or container with a public IP and domain name (e.g., `donald.example.com`)
- Python 3.11+
- API keys:
  - **Anthropic Claude** (free tier available; get at https://console.anthropic.com)
  - **Deepgram** (speech-to-text; free tier available; get at https://console.deepgram.com)
  - **ElevenLabs** (text-to-speech; free tier available; get at https://elevenlabs.io)
  - **Google Calendar + Gmail** (optional; for calendar/email tools; see setup below)

## Step 1: Set up the VM

```bash
# SSH into your VM
ssh user@your-vm-ip

# Install Caddy (simple HTTPS reverse proxy)
# https://caddyserver.com/docs/install
sudo apt-get update
sudo apt-get install -y caddy

# Install Python and pip
sudo apt-get install -y python3.11 python3.11-venv python3-pip

# Clone or upload the Donald repo
git clone https://github.com/yourusername/donald.git
cd donald
```

## Step 2: Configure environment variables

Create `.env` file with your API keys:

```bash
cat > .env << 'EOF'
# Server auth — long random string
BEARER_TOKEN=$(openssl rand -hex 32)

# API keys (get these from the provider dashboards)
ANTHROPIC_API_KEY=sk-ant-...
DEEPGRAM_API_KEY=...
ELEVENLABS_API_KEY=sk_...

# Google APIs (optional; leave empty to stub)
GOOGLE_CALENDAR_CREDENTIALS_JSON=/path/to/credentials.json
GMAIL_CREDENTIALS_JSON=/path/to/credentials.json

# Server config
HOST=127.0.0.1
PORT=8000
DEBUG=false

# Database
DB_PATH=/var/lib/donald/donald.db

# TTS cache TTL
TTS_CACHE_TTL_SECONDS=300
EOF

# Protect the .env file
chmod 600 .env
```

Generate a secure bearer token:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

## Step 3: Install Python dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Step 4: Configure Caddy

Caddy auto-provisions Let's Encrypt TLS and reverse-proxies HTTPS + WSS to your FastAPI server.

Create `Caddyfile`:

```caddy
donald.example.com {
    # Reverse proxy to FastAPI server
    reverse_proxy localhost:8000 {
        # Allow WebSocket upgrades
        header_up Connection *upgrade*
        header_up Upgrade websocket
    }

    # Disable ACME challenge (Caddy auto-renews)
    tls internal
}
```

Or with auto Let's Encrypt:

```caddy
donald.example.com {
    reverse_proxy localhost:8000 {
        header_up Connection *upgrade*
        header_up Upgrade websocket
    }
}
```

Load the Caddyfile:

```bash
sudo systemctl stop caddy
sudo caddy run --config Caddyfile
# Or in production:
sudo systemctl start caddy
```

Verify it's running:

```bash
curl https://donald.example.com/healthz
# Should return: {"status":"ok"}
```

## Step 5: Run the FastAPI server

In a separate terminal:

```bash
source venv/bin/activate
python3 -m uvicorn server.main:app --host 127.0.0.1 --port 8000 --log-level info
```

Or use a process manager like Systemd or Supervisor:

**systemd service** (`/etc/systemd/system/donald.service`):

```ini
[Unit]
Description=Donald Voice Agent
After=network.target

[Service]
Type=simple
User=donald
WorkingDirectory=/home/donald/donald
Environment="PATH=/home/donald/donald/venv/bin"
ExecStart=/home/donald/donald/venv/bin/python3 -m uvicorn server.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable and start:

```bash
sudo systemctl enable donald
sudo systemctl start donald
sudo systemctl status donald
```

## Step 6: Test the server

```bash
BEARER_TOKEN=$(grep BEARER_TOKEN .env | cut -d= -f2)

# Health check
curl -H "Authorization: Bearer $BEARER_TOKEN" https://donald.example.com/healthz

# Fetch shell
curl -H "Authorization: Bearer $BEARER_TOKEN" https://donald.example.com/ | head -20

# TTS endpoint (will fail without cached text, but tests auth)
curl -H "Authorization: Bearer $BEARER_TOKEN" https://donald.example.com/api/tts/fake-turn-id
```

## Step 7: Install on iOS

1. Open Safari on your iPhone.
2. Navigate to `https://donald.example.com`.
3. Tap the Share button (arrow up from bottom).
4. Scroll down and tap **"Add to Home Screen"**.
5. Name it "Donald" and tap **Add**.

The PWA now appears on your home screen. Tap to open.

**First use:** The app will ask for microphone permission. Tap **Allow**.

## Step 8: Real API Setup (Optional)

The tools are currently stubbed. To wire real APIs:

### Google Calendar & Gmail

1. Create a Google Cloud project: https://console.cloud.google.com
2. Enable APIs: Google Calendar API, Gmail API
3. Create OAuth 2.0 credentials (Desktop app).
4. Download the credentials JSON and save to the server.
5. Set `GOOGLE_CALENDAR_CREDENTIALS_JSON` and `GMAIL_CREDENTIALS_JSON` env vars.
6. Update `server/brain.py` tools to call the real APIs (use `google-auth` library).

### Deepgram STT

1. Get API key from https://console.deepgram.com
2. WebSocket streaming is already integrated in `server/deepgram.py`.

### ElevenLabs TTS

1. Get API key from https://elevenlabs.io
2. ElevenLabs HTTP streaming is already integrated in `server/elevenlabs.py`.

## Monitoring & Logs

View real-time logs:

```bash
sudo systemctl status donald
sudo journalctl -u donald -f
```

Check database:

```bash
sqlite3 /var/lib/donald/donald.db
sqlite> SELECT * FROM sessions LIMIT 5;
sqlite> SELECT role, text FROM turns ORDER BY created_at DESC LIMIT 10;
```

## Troubleshooting

### WebSocket connection fails

- Verify Caddy is forwarding WebSocket upgrades (`header_up Connection *upgrade*`).
- Check bearer token in PWA URL: `?token=YOUR_TOKEN`.

### TTS sounds robotic

- Adjust ElevenLabs voice settings in `server/elevenlabs.py` (`stability`, `similarity_boost`).
- Try a different voice ID.

### App disappears from home screen after update

- `Cache-Control: no-store` on the shell ensures fresh loads, but changes to `scene.js` and `voice.js` require versioned imports. Update the version in `frontend/index.html` (e.g., `?v=20260630-hotfix`).

### Microphone doesn't work

- iOS PWA requires HTTPS and user gesture (tap). Verify both.
- Check browser console for `getUserMedia` errors.

## Security Notes

- **Bearer token** is sent in three places: `Authorization` header, `X-Auth-Token` header, and `?token=` query param. All must validate via constant-time comparison.
- Token is used for both HTTP and WebSocket. Store it in a `.env` file and never commit it.
- The PWA shell (`/`) should serve with `Cache-Control: no-store` to force fresh loads and prevent stale deployments from being cached by iOS PWA.
- TTS responses are cached by `turn_id` with a TTL; they are not evicted on read (iOS Safari makes two GET requests).

## Next Steps

- Wire real tool implementations (calendar, email, weather APIs).
- Add conversation persistence to a shared database so phone and desktop clients share state.
- Implement confirmation flow for risky actions (send email, create event).
- Monitor tool execution latency and optimize LLM response streaming.

## Support

For issues or questions, see the codebase documentation in this repo.
