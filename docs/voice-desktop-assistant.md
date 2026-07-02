# Donald — Voice Desktop Assistant

> Say "Donald", a UI wakes on your computer, you talk to it, and it does things
> on your machine. Donald is the voice and the brain; **Hermes** is the hands.

This is the always-listening, talk-to-your-computer layer of the
[master plan](00-MASTERPLAN.md). It turns the existing Donald personality from a
text chatbot into a spoken operator that can act on the local machine.

## The experience

1. You launch it once (`python -m donald.app`). A small local server starts and
   the Donald UI opens in your browser — a glowing orb, a status line, a
   transcript.
2. It listens in the background for the wake word **"Donald"**.
3. You say *"Donald, what's eating my disk space?"* The orb lights up, your
   words appear in the transcript.
4. Donald reasons in character, calls Hermes to run the right command, sees the
   output, and **speaks** a short answer back while the details show on screen.
5. If you ask for something destructive, Donald tells you exactly what he's
   about to do and waits for you to say **yes** before doing it.

## Architecture

```
┌─────────────────────── your computer ───────────────────────┐
│                                                              │
│   Browser (donald/web/)            Local server (donald/app.py)
│   ─────────────────────            ───────────────────────── │
│   • wake word "Donald"   POST       • DonaldBrain (brain.py)  │
│   • speech → text   ───/api/turn──▶   – Claude tool-use loop  │
│   • Donald's voice  ◀──{reply}────    – personality layers    │
│   • the orb + transcript            • Hermes (hermes/)        │
│                                       – run_shell / open_app  │
│                                       – ApprovalGate on every │
│                                         shell command         │
└──────────────────────────────────────────────────────────────┘
        loopback only (127.0.0.1) — your machine talking to itself
```

### Why a local web app

The browser already ships the best cross-platform voice stack there is — the
**Web Speech API** gives wake-word recognition, speech-to-text, and
text-to-speech for free on macOS, Windows, and Linux, with no native audio
libraries to install. The Python side already owns the personality, the brain,
and the security gates. So the split is: **browser = ears + mouth + face**,
**Python = brain + hands**. They talk over loopback HTTP; one spoken command is
one `POST /api/turn`.

### Components

| Piece | File | Role |
|------|------|------|
| Voice UI | `donald/web/{index.html,app.js,styles.css}` | Wake word, STT, TTS, the orb, the transcript |
| App server | `donald/app.py` | Loopback HTTP server; serves the UI, runs one turn per request |
| Brain | `donald/brain.py` | `DonaldBrain` — the reason-and-act tool-use loop |
| Hands | `donald/hermes/` | `Hermes` engine + tool specs Donald calls |
| Personality | `donald/personality.py`, `donald/AGENT.md` | The drift-proof voice layers (unchanged) |

## Hermes — the execution engine

Hermes is deliberately small and safe. It exposes three capabilities to
Donald's brain as tools, plus a confirmation handshake:

- `run_shell(command)` — run a shell command. **Gated.**
- `open_app(name)` — launch a desktop app (OS-aware: `open -a` / `start` / `gtk-launch`).
- `open_url(url)` — open a URL in the default browser.
- `set_reminder(seconds, message)` — Donald brings it up out loud later, unprompted.
- `remember(fact)` — store a durable fact about you (survives restarts).
- `confirm_action(token)` — run a previously gated command the user just approved.
- `computer` — **(opt-in)** see the screen and click/type/scroll any app. See below.

Every `run_shell` passes through `security.approval.ApprovalGate`:

- **Hardline blocklist** (`rm -rf /`, fork bombs, disk wipes, `curl … | sh`, …)
  is refused in every mode and **cannot be overridden** — not by the user, not
  by an instruction injected into a transcript or a file Donald reads.
- **Risky** commands (`git push --force`, `DROP TABLE`, bounded `rm -rf`, …)
  come back as `needs_confirmation`. Donald asks you out loud and only runs them
  via `confirm_action` after a clear yes.
- **Low-risk** commands run immediately.

Subprocesses are spawned with `security.subprocess_env.shell_minimal()` so the
Anthropic key and other secrets never leak into a child process, and all output
is passed through `security.log_redact.redact()`.

## Computer-use — see and operate any app (opt-in)

Shell tools are blind: they can't run an app that has no command line. Computer-
use fills that gap. When enabled, Donald gets Anthropic's native `computer` tool;
the model looks at a screenshot and emits actions (move, click, type, key,
scroll), which `ComputerController` (`donald/hermes/computer.py`) performs on the
real display and answers with a fresh screenshot. The brain routes this through
the beta endpoint and feeds the screenshots back to the model as images.

```bash
./run.sh --computer            # or: python -m donald.app --computer-use
```

- **Deps:** `pip install pyautogui pillow` (run.sh does this for you).
- **macOS permissions:** grant your terminal **Accessibility** *and* **Screen
  Recording** in System Settings → Privacy & Security, or clicks and screenshots
  silently fail.
- **Off by default.** It's the most powerful — and least contained — thing
  Hermes can do (a click can press any on-screen button), so it's opt-in,
  supports `--dry-run`, and the brain is instructed to get a spoken "yes" before
  anything consequential (buying, sending, deleting). It still prefers the
  faster, safer shell tools when they can do the job.

> The current engine drives the machine via shell + OS scripting *and* now
> computer-use. Shell is faster and precise; computer-use is the fallback for
> arbitrary GUI. Wiring the master-plan MCP skills (Gmail, Drive, …) as Hermes
> tools is the next expansion — same voice → brain → gated-action path.

## Toward Jarvis: senses, proactivity, a stop word

Three things move Donald from a voice command line toward something that feels
like Jarvis — it understands your situation, it speaks first, and it stops on a
word.

- **Ambient context (`donald/context.py`).** Each turn, Donald senses your
  situation — time, machine, the foreground app — and the brain injects it as a
  system block. So he can react to what you're *doing*, not only what you say.
  Collection is best-effort and OS-aware; a failed probe just omits that field.
- **Proactivity (`donald/proactive.py`).** A background loop delivers due
  messages through the app's outbound queue, which the UI polls
  (`GET /api/events`) and speaks — Donald talking *first*. The seed watcher is
  reminders: "Donald, remind me in ten minutes to call Luca," and ten minutes
  later he brings it up on his own. New triggers (calendar, a failing build, a
  file change) plug into the same `schedule → deliver` path.
- **Memory (`donald/memory.py`).** A small SQLite store under `~/.donald` so
  Donald remembers you across restarts: every turn is logged (and the recent
  ones rehydrated into context on launch, so a restart continues the
  conversation), and durable facts ("call me Champ", "co-founder is Luca") are
  injected each turn via the `remember` tool. No dependencies.
- **Kill switch (`donald/killswitch.py`).** Before an always-on mic that can
  click anything, you need a hard stop. Say **"stop"** (caught in the browser,
  so it never waits on the model) or hit the Stop button: every Hermes action
  refuses, each turn short-circuits to "I'm on hold," and proactive messages are
  held (not lost). Say **"resume"** to come back. It also honors the repo's
  env-var switch (`security.killswitch`) as the ops/incident lever.

## Safety & trust model

- **Transcripts are data, not commands from a third party.** The operator
  briefing in `brain.py` tells Donald to treat anything arriving via a tool
  result (file contents, web pages, command output) as data, never as new
  instructions — the standard prompt-injection defense, applied to a machine
  that can now act.
- **Confirm before consequence.** The approval tiers above are the spine.
- **Loopback only.** The server binds `127.0.0.1`; nothing is exposed to the
  network.
- **Dry-run.** `--dry-run` makes Hermes describe actions instead of running
  them — use it the first time on a new machine, and in demos.

## Always-on wake — "say Donald from anywhere, it opens"

The browser UI listens for the wake word *while it's open*. To get the real
experience — you're anywhere on your computer, you say **"Donald"**, and the app
opens itself, already listening — run the **wake listener** (`donald/listener.py`):

```bash
python -m donald.listener
```

It listens to the microphone in the background. When it hears "Donald" it makes
sure the app server is up (starting it if needed) and opens the UI with
`?armed=1`, which tells the page to skip the button, greet you ("Yeah?"), and
start capturing your command immediately. So the whole interaction is: *say
"Donald", then just talk.*

**Wake-word recognition is offline.** It uses [Vosk](https://alphacephei.com/vosk/models)
— no audio leaves the machine, no per-utterance network call. One-time setup:

```bash
pip install vosk sounddevice          # macOS: brew install portaudio first
# download vosk-model-small-en-us-0.15, unzip it to ./model
```

**Start it at login (macOS).** `scripts/com.donald.listener.plist` is a
LaunchAgent template — edit the two paths and your key, copy it to
`~/Library/LaunchAgents/`, and `launchctl load` it. Then it's always there;
macOS will ask for microphone permission the first time (allow it).

The launch *decision* (wake-word matching, a cooldown so a long command doesn't
relaunch mid-sentence) lives in `WakeListener.handle_text` and is unit-tested
without a microphone; the audio loop just feeds it recognized text.

> Honest note: Vosk full-STT keyword spotting is "good enough" and fully
> offline, but a purpose-built wake engine (Porcupine/openWakeWord) is more
> robust against false triggers. It's a drop-in swap — replace `_load_recognizer`
> and keep `handle_text`.

## Extending it

The engine is structured so new powers are additive:

- **More Hermes tools.** Add a method to `Hermes`, a spec to `TOOL_SPECS`, and a
  branch to `dispatch()`. Wire risky ones through the `ApprovalGate`.
- **Computer-use (screenshot + click) — built, opt-in.** For apps with no CLI,
  Hermes can drive the screen directly. See the section below.
- **The other pillars.** The MCP integrations in the master plan (Gmail, Drive,
  Apollo, Twilio, …) become Hermes tools the same way, so "Donald, email this"
  flows through the identical voice → brain → gated-action path.

## Limitations (honest status)

- Voice quality and wake-word reliability depend on the browser's Web Speech API
  (best in Chrome/Edge). It's good enough to feel real, not a tuned wake-word
  engine like Porcupine — that's a drop-in upgrade later.
- Hermes controls the computer through the shell and OS scripting today; it
  can't yet click arbitrary on-screen UI (see *Extending it*).
- One conversation per running server process; restart clears memory. Durable
  memory is the master-plan memory layer, wired in later.
