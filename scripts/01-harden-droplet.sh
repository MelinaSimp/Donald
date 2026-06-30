#!/usr/bin/env bash
#
# Phase 2 — Harden a fresh Ubuntu 24.04 droplet.
# Run as root ON THE DROPLET:
#   ADMIN_USER=deploy HOME_IP=1.2.3.4 bash 01-harden-droplet.sh
#
# Creates a non-root sudo user, enables UFW (only 22 + 5432-from-home-IP),
# and turns on unattended security upgrades. Does NOT reboot.
set -euo pipefail

: "${ADMIN_USER:?set ADMIN_USER, e.g. ADMIN_USER=deploy}"
: "${HOME_IP:?set HOME_IP to your current public IP (UFW will allow 5432 only from it)}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root on the droplet." >&2
  exit 1
fi

echo "==> Updating base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

echo "==> Creating non-root sudo user: ${ADMIN_USER}"
if ! id -u "$ADMIN_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$ADMIN_USER"
fi
usermod -aG sudo "$ADMIN_USER"
# Passwordless sudo is convenient for automation; remove this file if you prefer
# to be prompted. SSH is still key-only, so this does not weaken remote access.
echo "${ADMIN_USER} ALL=(ALL) NOPASSWD:ALL" > "/etc/sudoers.d/90-${ADMIN_USER}"
chmod 440 "/etc/sudoers.d/90-${ADMIN_USER}"

echo "==> Hardening SSH (key-only, no root password login)"
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl restart ssh || systemctl restart sshd || true

echo "==> Configuring UFW (only 22 + 5432-from-home-IP)"
apt-get install -y ufw
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow from "$HOME_IP" to any port 5432 proto tcp comment 'Postgres from home IP'
ufw --force enable
ufw status verbose

echo "==> Enabling unattended-upgrades (automatic security patches)"
apt-get install -y unattended-upgrades
dpkg-reconfigure -f noninteractive unattended-upgrades
cat > /etc/apt/apt.conf.d/20auto-upgrades <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

echo
echo "==> Hardening complete."
echo "    UFW allows: 22/tcp (anywhere), 5432/tcp (from ${HOME_IP} only)."
echo "    Next: copy your SSH key to ${ADMIN_USER} and log in as them (see runbook Phase 2)."
echo "    NOTE: no reboot was performed."
