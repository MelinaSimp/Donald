#!/usr/bin/env bash
# Donald desktop launcher — one command instead of a CLI incantation each time.
#
#   ./desktop/donald.sh            start the gateway (if needed) + open the orb
#   ./desktop/donald.sh gateway    run the gateway in the FOREGROUND (for
#                                  launchd / systemd — they own the process)
#   ./desktop/donald.sh open       just open the orb app window
#   ./desktop/donald.sh status     is the gateway up? is Hermes reachable?
#   ./desktop/donald.sh stop       stop a background gateway started by this script
#
# To make it fully hands-off (starts at login, restarts if it dies), run
# desktop/install-macos.sh or desktop/install-linux.sh once. After that the
# only thing you ever do is CLAP.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE_DIR="${HOME}/.donald"
VENV="${ROOT}/.venv"
mkdir -p "${STATE_DIR}"

# Load the gateway env (keys, Hermes wiring) if present.
if [[ -f "${ROOT}/gateway/.env" ]]; then
  set -a; # shellcheck disable=SC1091
  source "${ROOT}/gateway/.env"; set +a
fi
PORT="${GATEWAY_PORT:-8765}"
URL="http://127.0.0.1:${PORT}"

ensure_venv() {
  if [[ ! -x "${VENV}/bin/python" ]]; then
    echo "donald: first run — creating venv + installing deps…"
    python3 -m venv "${VENV}"
    "${VENV}/bin/pip" install --quiet --upgrade pip
    "${VENV}/bin/pip" install --quiet -r "${ROOT}/requirements.txt"
  fi
}

healthy() { curl -sf --max-time 2 "${URL}/health" >/dev/null 2>&1; }

start_gateway_bg() {
  if healthy; then
    echo "donald: gateway already up at ${URL}"
    return 0
  fi
  ensure_venv
  echo "donald: starting gateway at ${URL} (log: ${STATE_DIR}/gateway.log)"
  nohup "${VENV}/bin/python" -m gateway.server \
    >>"${STATE_DIR}/gateway.log" 2>&1 &
  echo $! > "${STATE_DIR}/gateway.pid"
  for _ in $(seq 1 40); do
    healthy && { echo "donald: gateway is up"; return 0; }
    sleep 0.5
  done
  echo "donald: gateway did not come up — check ${STATE_DIR}/gateway.log" >&2
  return 1
}

open_orb() {
  # Prefer a chromium-family browser in APP MODE with its own profile:
  #  - looks like a native window (no tabs/URL bar),
  #  - mic permission persists in the dedicated profile,
  #  - autoplay flag lets Donald speak without a click first.
  local flags=(
    "--app=${URL}"
    "--user-data-dir=${STATE_DIR}/orb-profile"
    "--autoplay-policy=no-user-gesture-required"
    "--no-first-run" "--no-default-browser-check"
  )
  local candidates=()
  case "$(uname -s)" in
    Darwin)
      candidates=(
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        "/Applications/Chromium.app/Contents/MacOS/Chromium"
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
      )
      ;;
    *)
      candidates=(google-chrome google-chrome-stable chromium chromium-browser brave-browser microsoft-edge)
      ;;
  esac
  for c in "${candidates[@]}"; do
    if command -v "$c" >/dev/null 2>&1 || [[ -x "$c" ]]; then
      echo "donald: opening orb app window (${c##*/})"
      "$c" "${flags[@]}" >/dev/null 2>&1 &
      return 0
    fi
  done
  echo "donald: no chromium-family browser found — opening ${URL} in the default browser"
  case "$(uname -s)" in
    Darwin) open "${URL}" ;;
    *) xdg-open "${URL}" >/dev/null 2>&1 || echo "donald: open ${URL} yourself" ;;
  esac
}

case "${1:-}" in
  gateway)
    ensure_venv
    cd "${ROOT}"
    exec "${VENV}/bin/python" -m gateway.server
    ;;
  open)
    open_orb
    ;;
  status)
    if healthy; then
      echo "donald: gateway UP at ${URL}"
      curl -s "${URL}/health"; echo
    else
      echo "donald: gateway DOWN (${URL})"
      exit 1
    fi
    ;;
  stop)
    if [[ -f "${STATE_DIR}/gateway.pid" ]]; then
      kill "$(cat "${STATE_DIR}/gateway.pid")" 2>/dev/null && echo "donald: gateway stopped" \
        || echo "donald: gateway was not running"
      rm -f "${STATE_DIR}/gateway.pid"
    else
      echo "donald: no background gateway pidfile (was it started by launchd/systemd?)"
    fi
    ;;
  ""|start)
    cd "${ROOT}"
    start_gateway_bg
    open_orb
    ;;
  *)
    echo "usage: donald.sh [start|gateway|open|status|stop]" >&2
    exit 2
    ;;
esac
