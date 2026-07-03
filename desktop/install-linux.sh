#!/usr/bin/env bash
# Make Donald a permanent resident of this Linux desktop:
#   - the gateway runs as a systemd USER service (starts at login, restarts on crash)
#   - the orb app window opens at login via XDG autostart
#
#   ./desktop/install-linux.sh          install + start now
#   ./desktop/install-linux.sh remove   uninstall
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UNIT_DIR="${HOME}/.config/systemd/user"
AUTOSTART_DIR="${HOME}/.config/autostart"
UNIT="${UNIT_DIR}/donald-gateway.service"
DESKTOP="${AUTOSTART_DIR}/donald-orb.desktop"
mkdir -p "${UNIT_DIR}" "${AUTOSTART_DIR}" "${HOME}/.donald"

if [[ "${1:-}" == "remove" ]]; then
  systemctl --user disable --now donald-gateway.service 2>/dev/null || true
  rm -f "${UNIT}" "${DESKTOP}"
  systemctl --user daemon-reload
  echo "donald: removed."
  exit 0
fi

cat > "${UNIT}" <<UNIT
[Unit]
Description=Donald gateway (brain + Hermes bridge + voice)
After=network.target

[Service]
Type=exec
ExecStart=${ROOT}/desktop/donald.sh gateway
WorkingDirectory=${ROOT}
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
UNIT

cat > "${DESKTOP}" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Donald Orb
Comment=Donald's orb — clap to wake
Exec=${ROOT}/desktop/donald.sh open
X-GNOME-Autostart-enabled=true
DESKTOP

systemctl --user daemon-reload
systemctl --user enable --now donald-gateway.service

echo "donald: installed."
echo "  gateway  -> systemctl --user status donald-gateway"
echo "  orb      -> opens at login (${DESKTOP}); open now: ${ROOT}/desktop/donald.sh open"
echo
echo "First time only: when the orb window opens, allow the microphone —"
echo "the dedicated browser profile remembers it forever after."
