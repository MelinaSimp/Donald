# Donald on the desktop — always on, clap to wake

No more `cd … && python -m …` every time. Donald becomes a resident of the
machine: the **gateway** runs permanently in the background, the **orb** opens
as its own app window, and a **loud clap** is the only interface you need.

```
   👏  CLAP (loud enough — talking won't do it)
    │
    ▼
  ORB turns gold, chimes, listens          ← the show
    │  your words → speech-to-text
    ▼
  DONALD (brain) decides, delegates ──▶ HERMES (local agent: terminal,
    │                                    files, apps, web — your desktop)
    ▼
  Donald talks back; the OPS TERMINAL page logged every step of it
```

## One-time setup

```bash
cp gateway/.env.example gateway/.env   # fill in keys + Hermes wiring
./desktop/donald.sh                    # start gateway + open the orb window
```

First launch creates a venv, installs deps, and opens the orb at
`http://127.0.0.1:8765`. Allow the **microphone** when asked — the dedicated
browser profile (`~/.donald/orb-profile`) remembers the choice permanently.

## Make it permanent (starts at login, restarts if it dies)

```bash
./desktop/install-macos.sh    # macOS: launchd agents
./desktop/install-linux.sh    # Linux: systemd user service + autostart window
```

Uninstall any time with `./desktop/install-macos.sh remove` (or the Linux
equivalent).

## The clap gate — "it has to be loud enough"

Waking is deliberately hard to trigger by accident. A sound only wakes Donald
if it passes **all four** tests:

1. **Loud** — the peak must clear the loudness gate (the slider in the
   top-right of the orb; higher = a louder clap is required).
2. **Sudden** — the room must be comparatively quiet right before it, so a
   loud word mid-sentence is rejected.
3. **Short** — the energy must collapse within ~200 ms; shouting, music, or a
   dragged chair sustains and is rejected.
4. **Above the room** — the peak must dwarf the rolling noise floor, so a
   generally loud room raises the bar instead of tripping it.

Watch the little level meter under the 👂 chip: the bar flashes orange when a
sound clears the gate. Clap, check the meter, and drag the slider until *your*
clap lands past it but your voice never does. The setting is remembered.

## The pages

- **Orb** (default) — the show. Gold = listening, teal/violet churn =
  thinking, orange = speaking. Hermes' avatar docks by its panel and pulses
  while it's working on your machine.
- **OPS TERMINAL** — press **`** (backtick), **T**, or the ⌨ button. A full
  terminal view tracking *everything*: your transcript, Donald's replies,
  every delegation to Hermes (task + why), Hermes' own output **streamed
  line-by-line while it works**, results, flags, errors — timestamped. There's
  a prompt at the bottom, so you can also just type to Donald.

## The agentic part — Hermes does the real work

Donald never touches the machine himself; anything real (open apps, run
commands, read/write files, browse) is delegated to **Hermes**, the local
agent on your desktop, via the gateway. Wire it in `gateway/.env`:

- `HERMES_MODE=cli` — drives Hermes' one-shot CLI (`hermes -z "<task>" --yolo`),
  through `docker exec` if `HERMES_DOCKER_CONTAINER` is set. Run the gateway on
  the same host as the container.
- `HERMES_MODE=http` — points at Hermes' OpenAI-compatible API server
  (`HERMES_BASE_URL`, default `http://127.0.0.1:8642`).

Check the link end-to-end with `./desktop/donald.sh status` — it reports
whether the brain is configured and whether Hermes is reachable. The terminal
page's header shows the same as live chips.

`--yolo` means Hermes auto-approves its own tool use, which is what makes the
whole loop hands-free ("you can go on desktop, whatever you need to do").
Everything Hermes returns is still treated as **untrusted data** (injection-
gated and flagged in the terminal), and logs are redacted.

## Troubleshooting

| Symptom | Fix |
|---|---|
| Clap never wakes it | Lower the loudness gate slider; check the 👂 chip says **armed** (click it to re-arm); make sure the meter moves when you make noise. |
| Talking wakes it | Raise the slider — the gate is absolute loudness, so set it above your voice's peaks. |
| "gateway offline" in the terminal page | `./desktop/donald.sh status`, then `~/.donald/gateway.log`. |
| "Hermes not reachable" | Check `HERMES_MODE` and the container name (`docker ps`), or that the API server is up on `:8642`. |
| No spoken reply | Set `ELEVENLABS_API_KEY` in `gateway/.env` (`VOICE_ENABLED=true`). Without it Donald falls back to the browser's built-in voice. |
| Speech-to-text does nothing | Use a chromium-family browser (the launcher picks one automatically) — it provides the Web Speech API. |
