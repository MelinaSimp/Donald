#!/usr/bin/env bash
# Make Donald a permanent resident of this Mac:
#   - the gateway runs at login and is restarted if it ever dies (launchd)
#   - the orb app window opens at login
# After this you never touch a terminal again — you just clap.
#
#   ./desktop/install-macos.sh          install + start now
#   ./desktop/install-macos.sh remove   uninstall both agents
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTS_DIR="${HOME}/Library/LaunchAgents"
GATEWAY_PLIST="${AGENTS_DIR}/com.donald.gateway.plist"
ORB_PLIST="${AGENTS_DIR}/com.donald.orb.plist"
LOG_DIR="${HOME}/.donald"
mkdir -p "${AGENTS_DIR}" "${LOG_DIR}"

if [[ "${1:-}" == "remove" ]]; then
  launchctl unload "${GATEWAY_PLIST}" 2>/dev/null || true
  launchctl unload "${ORB_PLIST}" 2>/dev/null || true
  rm -f "${GATEWAY_PLIST}" "${ORB_PLIST}"
  echo "donald: launch agents removed."
  exit 0
fi

# 1) Gateway: KeepAlive daemon — always on, restarts on crash.
cat > "${GATEWAY_PLIST}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.donald.gateway</string>
  <key>ProgramArguments</key>
  <array>
    <string>${ROOT}/desktop/donald.sh</string>
    <string>gateway</string>
  </array>
  <key>WorkingDirectory</key><string>${ROOT}</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>${LOG_DIR}/gateway.log</string>
  <key>StandardErrorPath</key><string>${LOG_DIR}/gateway.log</string>
</dict>
</plist>
PLIST

# 2) Orb window: opens once at login (not kept alive — closing it is allowed;
#    clap-wake needs the window running, so reopen with donald.sh open).
cat > "${ORB_PLIST}" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.donald.orb</string>
  <key>ProgramArguments</key>
  <array>
    <string>${ROOT}/desktop/donald.sh</string>
    <string>open</string>
  </array>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>${LOG_DIR}/orb.log</string>
  <key>StandardErrorPath</key><string>${LOG_DIR}/orb.log</string>
</dict>
</plist>
PLIST

launchctl unload "${GATEWAY_PLIST}" 2>/dev/null || true
launchctl unload "${ORB_PLIST}" 2>/dev/null || true
launchctl load "${GATEWAY_PLIST}"
launchctl load "${ORB_PLIST}"

echo "donald: installed."
echo "  gateway  -> runs at login, auto-restarts (com.donald.gateway)"
echo "  orb      -> opens at login (com.donald.orb)"
echo "  logs     -> ${LOG_DIR}/gateway.log"
echo
echo "First time only: when the orb window opens, allow the microphone —"
echo "the dedicated browser profile remembers it forever after."
