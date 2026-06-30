#!/usr/bin/env bash
#
# Phase 3 — Install & configure Postgres with TLS and password-only remote access.
# Run as the NON-ROOT admin user ON THE DROPLET (it uses sudo):
#   APP_DB=assistant APP_DB_USER=assistant_app DROPLET_IP=203.0.113.10 bash 02-setup-postgres.sh
#
# - installs latest stable Postgres from the official PGDG apt repo
# - creates role $APP_DB_USER with a RANDOM password (printed ONCE here only)
# - creates database $APP_DB owned by that role
# - generates a self-signed TLS cert, ssl = on
# - listen_addresses = '*'  (UFW is the gatekeeper)
# - pg_hba.conf: all remote connections require hostssl + scram password
#
# SECURITY: the generated password is printed exactly once to THIS terminal.
# Copy it into your password manager now. It is never written to the repo or chat.
set -euo pipefail

: "${APP_DB:?set APP_DB, e.g. APP_DB=assistant}"
: "${APP_DB_USER:?set APP_DB_USER, e.g. APP_DB_USER=assistant_app}"
: "${DROPLET_IP:?set DROPLET_IP to the droplet public IP (used as cert CN)}"

echo "==> Installing Postgres from the official PGDG apt repo"
sudo install -d /usr/share/postgresql-common/pgdg
sudo curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
  -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc
. /etc/os-release
echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
  | sudo tee /etc/apt/sources.list.d/pgdg.list >/dev/null
sudo apt-get update -y
sudo apt-get install -y postgresql postgresql-contrib openssl

# Discover the installed major version and its config/data dirs.
PG_BIN_VER="$(ls /usr/lib/postgresql/ | sort -n | tail -1)"
PG_CONF_DIR="/etc/postgresql/${PG_BIN_VER}/main"
PG_DATA_DIR="/var/lib/postgresql/${PG_BIN_VER}/main"
echo "==> Detected Postgres ${PG_BIN_VER} (conf: ${PG_CONF_DIR})"

echo "==> Generating a strong random password for ${APP_DB_USER}"
# 32 url-safe bytes; lives only in this shell variable + the role we create.
APP_DB_PASSWORD="$(openssl rand -base64 32 | tr -d '/+=' | cut -c1-32)"

echo "==> Creating role and database"
sudo -u postgres psql -v ON_ERROR_STOP=1 <<SQL
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '${APP_DB_USER}') THEN
    CREATE ROLE ${APP_DB_USER} LOGIN PASSWORD '${APP_DB_PASSWORD}';
  ELSE
    ALTER ROLE ${APP_DB_USER} WITH LOGIN PASSWORD '${APP_DB_PASSWORD}';
  END IF;
END
\$\$;
SQL
# Create the DB only if it does not already exist, owned by the app role.
if ! sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${APP_DB}'" | grep -q 1; then
  sudo -u postgres createdb -O "${APP_DB_USER}" "${APP_DB}"
fi
# Force scram-sha-256 for the app role's stored password.
sudo -u postgres psql -v ON_ERROR_STOP=1 -c "SET password_encryption = 'scram-sha-256'; ALTER ROLE ${APP_DB_USER} WITH PASSWORD '${APP_DB_PASSWORD}';"

echo "==> Generating self-signed TLS certificate (CN=${DROPLET_IP})"
sudo openssl req -new -x509 -days 825 -nodes -text \
  -out "${PG_DATA_DIR}/server.crt" \
  -keyout "${PG_DATA_DIR}/server.key" \
  -subj "/CN=${DROPLET_IP}"
sudo chmod 600 "${PG_DATA_DIR}/server.key"
sudo chown postgres:postgres "${PG_DATA_DIR}/server.key" "${PG_DATA_DIR}/server.crt"

echo "==> Editing postgresql.conf (ssl on, listen on all interfaces, scram)"
sudo sed -i "s/^#\?listen_addresses.*/listen_addresses = '*'/" "${PG_CONF_DIR}/postgresql.conf"
sudo sed -i "s/^#\?ssl .*/ssl = on/" "${PG_CONF_DIR}/postgresql.conf"
sudo sed -i "s|^#\?ssl_cert_file.*|ssl_cert_file = 'server.crt'|" "${PG_CONF_DIR}/postgresql.conf"
sudo sed -i "s|^#\?ssl_key_file.*|ssl_key_file = 'server.key'|" "${PG_CONF_DIR}/postgresql.conf"
sudo sed -i "s/^#\?password_encryption.*/password_encryption = scram-sha-256/" "${PG_CONF_DIR}/postgresql.conf"

echo "==> Rewriting pg_hba.conf (remote = hostssl + scram only)"
# Local socket stays trust/peer for admin; ALL remote (v4+v6) must use TLS + password.
sudo tee "${PG_CONF_DIR}/pg_hba.conf" >/dev/null <<HBA
# Managed by 02-setup-postgres.sh — remote access requires TLS + scram password.
local   all   postgres                              peer
local   all   all                                   scram-sha-256
hostssl all   ${APP_DB_USER}   0.0.0.0/0            scram-sha-256
hostssl all   ${APP_DB_USER}   ::/0                 scram-sha-256
# Plain (non-SSL) host lines intentionally omitted: no unencrypted remote auth.
HBA

echo "==> Restarting Postgres"
sudo systemctl restart "postgresql@${PG_BIN_VER}-main" || sudo systemctl restart postgresql
sleep 2

echo "==> Verifying it listens on the public interface"
sudo ss -tlnp | grep ':5432' || { echo "ERROR: nothing listening on 5432" >&2; exit 1; }

echo
echo "============================================================"
echo " Postgres ${PG_BIN_VER} is configured."
echo "   database : ${APP_DB}"
echo "   role     : ${APP_DB_USER}"
echo "   TLS      : on (self-signed, CN=${DROPLET_IP})  -> use sslmode=require"
echo
echo " >>> COPY THIS PASSWORD INTO YOUR PASSWORD MANAGER NOW <<<"
echo " >>> It will NOT be shown again. <<<"
echo
echo "   ${APP_DB_USER} password: ${APP_DB_PASSWORD}"
echo
echo " Connection string template (fill the password from your manager):"
echo "   postgresql://${APP_DB_USER}:<PASSWORD>@${DROPLET_IP}:5432/${APP_DB}?sslmode=require"
echo "============================================================"

# Scrub the password from the shell variable.
unset APP_DB_PASSWORD
