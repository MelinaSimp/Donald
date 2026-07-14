# Deployment

How to run Donald in production, and the concrete setup for the two milestones
that **cannot be built or verified in a headless CI container** — the Tauri
desktop wrapper (M3) and code-signing / auto-update (M6). Those need a real build
machine (macOS + Windows) and paid developer certificates, so they're documented
here as setup guides rather than shipped as unverified code.

## The server (backend + gateway + web shell)

One process serves everything (`serve.py`):

```bash
pip install -r requirements.txt
export DATABASE_URL=postgresql://user:pass@host:5432/donald   # SQLite if unset
export BACKEND_SECRET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
export ANTHROPIC_API_KEY=sk-ant-...
# optional: OAuth (M4), Stripe (M5), embeddings — see .env.example
uvicorn "serve:create_app" --factory --host 0.0.0.0 --port 8000
```

Routes: `/app` (web shell), `/auth/*`, `/integrations/*`, `/oauth/*`,
`/billing/*`, `/runs`, `/api/chat`, `/ws`. Migrations run automatically at
startup. Put it behind TLS (a reverse proxy or a platform like Fly/Render), set
`OAUTH_REDIRECT_BASE` to the public URL, and point Stripe/OAuth callbacks at it.

## M3 — desktop wrapper (Tauri)

The web shell (`webui/`) is already the renderer; the desktop app is a thin
Tauri wrapper around it. **Build on a real macOS and Windows machine** (Tauri
needs Rust + the OS webview toolchain; it can't build headless).

1. `npm create tauri-app@latest` (or add Tauri to an existing front-end).
2. Point the Tauri window at the shell — either load the hosted URL
   (`"build": { "devUrl": "https://app.yourdomain.com/app" }`) or bundle
   `webui/` as the `frontendDist` and have it call the API at your server.
3. Add a browser-based **device-code / OAuth login**: open the system browser to
   the server, receive the bearer token back via a deep link, store it in the OS
   keychain (the shell already persists a token; the desktop build swaps
   `localStorage` for secure storage).
4. Global hotkey + native notifications via Tauri plugins.

## M6 — code-signing, notarization, auto-update

Unglamorous and mandatory; budget real time and **start the certificate
paperwork early** (certs have lead time).

- **macOS**: an Apple Developer ID Application cert; sign the `.app`, then
  notarize with `notarytool` and staple. Without this, Gatekeeper blocks launch.
- **Windows**: an Authenticode (OV/EV) cert; sign the `.msi`/`.exe` so SmartScreen
  doesn't warn.
- **Auto-update**: Tauri's updater checks an endpoint that returns the latest
  version + a signed artifact URL. Mirror the classic pattern —
  `GET /api/update/install/{mac,windows}` served from object storage (S3/R2) —
  and configure the updater's public key so only your signed builds install.
- **Delivery**: upload signed artifacts to object storage on release (CI on a
  signing-capable runner), and keep the update manifest pointing at the newest.

## Status of these in this repo

- Server, web shell, auth, memory, OAuth broker, and billing are implemented and
  tested here (SQLite + verified against live Postgres).
- The Tauri project, signing config, and update endpoint are **not** in the repo
  yet — they belong on a signing-capable build pipeline, per the guides above.
