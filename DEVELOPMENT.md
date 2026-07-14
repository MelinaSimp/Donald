# Development & release

How to run Donald in dev, build the desktop app, sign it, and wire up
third-party keys. The Tauri build and updater-signing steps below were run and
verified on Linux in this repo; the macOS/Windows signing steps need those OSes
and paid certificates, so they're written as exact recipes to run there.

## 1. Run the server (backend + gateway + web shell)

```bash
pip install -r requirements.txt
export BACKEND_SECRET_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
export ANTHROPIC_API_KEY=sk-ant-...            # else the offline mock brain
# DATABASE_URL=postgresql://…  (SQLite dev file if unset)
uvicorn "serve:create_app" --factory --host 0.0.0.0 --port 8000
```

Check what's configured any time:

```bash
python scripts/check_config.py
```

## 2. Third-party keys

Everything degrades gracefully — a missing key just disables that path, and
`check_config.py` shows the state. Copy `.env.example` and fill what you need.

| Key(s) | Unlocks | Where to get it |
|--------|---------|-----------------|
| `BACKEND_SECRET_KEY` | Encrypts integration tokens at rest (**required**) | `Fernet.generate_key()` |
| `ANTHROPIC_API_KEY` | The model brain | console.anthropic.com |
| `DATABASE_URL` | Postgres in prod | your Postgres host |
| `EMBEDDINGS_PROVIDER` + `_BASE_URL`/`_API_KEY` | Learned memory embeddings | OpenAI/Voyage/local |
| `GOOGLE_/GITHUB_/SLACK_CLIENT_ID`+`_SECRET` | Connect those integrations (M4) | each provider's OAuth app |
| `OAUTH_REDIRECT_BASE` | OAuth callback base URL | your public URL |
| `STRIPE_SECRET_KEY` / `STRIPE_PRICE_ID` / `STRIPE_WEBHOOK_SECRET` | Billing (M5) | dashboard.stripe.com |
| `DEEPGRAM_API_KEY` / `ELEVENLABS_API_KEY` | HQ voice (browser speech works without) | each service |
| `UPDATE_MANIFEST_PATH` | Serve desktop auto-updates (M6) | your release pipeline |

Each provider's OAuth callback URL is `${OAUTH_REDIRECT_BASE}/oauth/{provider}/callback`.
Stripe's webhook URL is `${OAUTH_REDIRECT_BASE}/billing/webhook`.

## 3. Desktop app (Tauri) — `desktop/`

The desktop app is a thin native shell: it opens a window on your Donald server
(prompting once for the URL, then auto-reconnecting) and adds auto-update.

**Prereqs:** Rust + Node. Linux also needs the webview libs:
`libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev`.

```bash
cd desktop
npm install
npm run dev                 # hot-reload dev window
npm run build               # release binary + installers for the current OS
```

Verified on Linux: `npm run build` produces `target/release/donald-os` (a ~7.5 MB
binary) and `…/bundle/deb/Donald OS_0.1.0_amd64.deb`. macOS produces `.app`/`.dmg`
and Windows `.msi`/`.exe` from the same config, run on those machines.

To point the icons somewhere else or change the window, edit
`src-tauri/tauri.conf.json`; regenerate icons from a 1024² PNG with
`npm run icon`.

## 4. Update signing (verified)

Auto-updates must be signed with a Tauri updater key so only your builds install.

```bash
cd desktop
npx tauri signer generate -w ~/.donald/updater.key      # prints the public key
```

- Put the **public** key in `src-tauri/tauri.conf.json` → `plugins.updater.pubkey`.
  (The repo ships a demo public key so it builds out of the box — **regenerate
  your own for production**; the demo private key is not distributed, so nobody
  can sign updates for it.)
- Keep the **private** key secret. In CI set:
  ```bash
  export TAURI_SIGNING_PRIVATE_KEY="$(cat ~/.donald/updater.key)"
  export TAURI_SIGNING_PRIVATE_KEY_PASSWORD="…"
  npm run build     # emits the installer AND a matching .sig
  ```
  Verified: this produces `Donald OS_0.1.0_amd64.deb` **and** `.deb.sig`.

## 5. OS code-signing & notarization (needs certs + the OS)

Update-signing (above) proves the artifact came from you; OS code-signing stops
Gatekeeper/SmartScreen from blocking launch. Separate keys, separate step.

- **macOS** — Apple Developer ID Application cert. Set `APPLE_CERTIFICATE`,
  `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY`, `APPLE_ID`,
  `APPLE_PASSWORD`, `APPLE_TEAM_ID`; `npm run build` signs, then notarizes with
  `notarytool` and staples.
- **Windows** — Authenticode (OV/EV) cert. Set the thumbprint under
  `bundle.windows.certificateThumbprint` (or use a signing service) so the
  `.msi`/`.exe` is signed.

Run these on a signing-capable runner (e.g. GitHub Actions macos-latest /
windows-latest); they can't be done on Linux.

## 6. Update delivery (M6) — the loop

1. On release, sign the artifacts (§4), upload them to object storage (S3/R2).
2. Write a manifest JSON and point `UPDATE_MANIFEST_PATH` at it:
   ```json
   {
     "version": "0.2.0", "notes": "…", "pub_date": "2026-07-14T00:00:00Z",
     "platforms": {
       "linux-x86_64":   {"url": "https://cdn/…AppImage", "signature": "<.sig>"},
       "darwin-aarch64": {"url": "https://cdn/…app.tar.gz", "signature": "<.sig>"},
       "windows-x86_64": {"url": "https://cdn/…msi.zip", "signature": "<.sig>"}
     }
   }
   ```
3. The desktop updater polls `GET /api/update/{target}/{arch}/{current_version}`
   (implemented in `backend/updates.py`): it returns **204** when the client is
   current, or the signed manifest entry when a newer build exists. The endpoint
   is tested in `tests/test_updates.py`.
