#!/usr/bin/env bash
#
# Donald — one-command launcher.
#
#   ./run.sh             Set up (once) and start Donald. Opens the UI; click
#                        "Wake Donald", allow the mic, and say "Donald".
#   ./run.sh --listen    Also start the always-on wake listener, so you can
#                        say "Donald" from anywhere and the app opens itself.
#                        (Installs the offline voice deps + model on first run.)
#
# It creates a local virtualenv, installs dependencies, loads your API key from
# a .env file if present, and starts everything. Re-running is cheap — setup
# steps are skipped when already done.

set -euo pipefail

cd "$(dirname "$0")"
VENV=".venv"
PY="$VENV/bin/python"
WITH_LISTENER=0
[ "${1:-}" = "--listen" ] && WITH_LISTENER=1

say() { printf "\033[1;33m▸ %s\033[0m\n" "$1"; }   # gold, on-brand
die() { printf "\033[1;31m✗ %s\033[0m\n" "$1" >&2; exit 1; }

# --- 1. Python ----------------------------------------------------------------
command -v python3 >/dev/null 2>&1 || die "python3 not found. Install Python 3.9+ (e.g. 'brew install python')."

if [ ! -d "$VENV" ]; then
  say "Creating virtualenv (.venv)…"
  python3 -m venv "$VENV"
fi

# --- 2. Dependencies ----------------------------------------------------------
say "Installing dependencies…"
"$PY" -m pip install --quiet --upgrade pip
"$PY" -m pip install --quiet -r requirements.txt

# --- 3. API key ---------------------------------------------------------------
# Load .env if present so you don't have to export the key every time.
if [ -f .env ]; then
  set -a; . ./.env; set +a
fi
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  die "ANTHROPIC_API_KEY is not set. Put it in a .env file (see .env.example) or 'export' it, then re-run."
fi

# --- 4. Optional: offline wake listener ---------------------------------------
if [ "$WITH_LISTENER" = "1" ]; then
  say "Setting up the always-on wake listener…"
  if ! "$PY" -c "import vosk, sounddevice" >/dev/null 2>&1; then
    if [ "$(uname)" = "Darwin" ] && ! (command -v brew >/dev/null 2>&1 && brew list portaudio >/dev/null 2>&1); then
      echo "  (macOS) sounddevice needs PortAudio. If install fails, run: brew install portaudio"
    fi
    "$PY" -m pip install --quiet vosk sounddevice || die "Could not install voice deps. On macOS: 'brew install portaudio' then re-run."
  fi
  if [ ! -d model ]; then
    say "Downloading the small offline speech model (~40 MB, one time)…"
    MODEL_ZIP="vosk-model-small-en-us-0.15.zip"
    curl -fL "https://alphacephei.com/vosk/models/$MODEL_ZIP" -o "$MODEL_ZIP" \
      || die "Model download failed. Grab it from https://alphacephei.com/vosk/models and unzip to ./model"
    unzip -q "$MODEL_ZIP" && mv "vosk-model-small-en-us-0.15" model && rm -f "$MODEL_ZIP"
  fi
fi

# --- 5. Launch ----------------------------------------------------------------
PIDS=()
cleanup() { for p in "${PIDS[@]:-}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT INT TERM

if [ "$WITH_LISTENER" = "1" ]; then
  say "Starting Donald (server + wake listener). Say \"Donald\" from anywhere. Ctrl-C to stop."
  "$PY" -m donald.app --no-browser & PIDS+=("$!")
  sleep 1
  "$PY" -m donald.listener & PIDS+=("$!")
  wait
else
  say "Starting Donald. The UI will open — click \"Wake Donald\", allow the mic, say \"Donald\". Ctrl-C to stop."
  "$PY" -m donald.app
fi
