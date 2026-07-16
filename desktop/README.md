# Donald OS — desktop (Tauri)

A thin native shell around the Donald web app: it opens a window on your server
(`/app`), auto-reconnects on next launch, and auto-updates. See the repo's
[`DEVELOPMENT.md`](../DEVELOPMENT.md) for the full build / sign / release guide.

## Build

```bash
npm install
npm run dev      # dev window with hot reload
npm run build    # release binary + installers for this OS
```

Linux also needs: `libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev`.
Verified on Linux → `src-tauri/target/release/donald-os` + a `.deb`. macOS/Windows
produce `.dmg`/`.msi` from the same config on those machines.

## Layout

| Path | What |
|------|------|
| `src-tauri/tauri.conf.json` | Window, bundle, icons, updater endpoint + public key |
| `src-tauri/src/lib.rs` | Registers the updater + shell plugins |
| `src-tauri/capabilities/default.json` | Window permissions (updater, open links) |
| `dist/index.html` | First-run "connect to your server" screen + update check |
| `src-tauri/icons/` | App icons (regenerate with `npm run icon` from a 1024² PNG) |

## Notes

- The `pubkey` in `tauri.conf.json` is a **demo** updater key so the project
  builds out of the box. **Generate your own for production** (`DEVELOPMENT.md` §4);
  the demo private key isn't distributed.
- Point the app at a server by entering its URL on first launch (defaults to
  `http://localhost:8000`); it's remembered after that.
