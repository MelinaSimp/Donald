#!/usr/bin/env bash
#
# Phase 5 — Non-destructive data migration: local Postgres -> cloud Postgres.
# Run ON YOUR LAPTOP (needs access to both the local DB and the droplet):
#   APP_DB=assistant APP_DB_USER=assistant_app DROPLET_IP=203.0.113.10 \
#   LOCAL_DB=assistant bash 03-migrate-data.sh
#
# Order of operations (per the hard rules):
#   1. pg_dump from local  (does NOT touch/drop local data)
#   2. restore into cloud
#   3. verify row counts table-by-table, local vs cloud
#
# You will be prompted for the cloud password (saved in your password manager).
set -euo pipefail

: "${APP_DB:?set APP_DB}"
: "${APP_DB_USER:?set APP_DB_USER}"
: "${DROPLET_IP:?set DROPLET_IP}"
: "${LOCAL_DB:?set LOCAL_DB (your existing local database name)}"

LOCAL_DSN="${LOCAL_DSN:-postgresql:///${LOCAL_DB}}"      # override if local needs host/user
CLOUD_DSN="postgresql://${APP_DB_USER}@${DROPLET_IP}:5432/${APP_DB}?sslmode=require"

WORKDIR="$(mktemp -d)"
DUMP="${WORKDIR}/${LOCAL_DB}.dump"
echo "==> Work dir: ${WORKDIR}"

echo "==> [1/3] Dumping local DB (custom format, non-destructive)"
pg_dump --format=custom --no-owner --no-privileges --file="${DUMP}" "${LOCAL_DSN}"
echo "    dump size: $(du -h "${DUMP}" | cut -f1)"

echo "==> [2/3] Restoring into cloud DB"
# --clean --if-exists makes re-runs idempotent on the CLOUD side only.
# The LOCAL database is never modified by this script.
pg_restore --no-owner --no-privileges --clean --if-exists \
  --dbname="${CLOUD_DSN}" "${DUMP}"

echo "==> [3/3] Verifying row counts table-by-table"
COUNT_SQL="
SELECT table_schema || '.' || table_name AS tbl,
       (xpath('/row/c/text()',
         query_to_xml(format('SELECT count(*) AS c FROM %I.%I', table_schema, table_name),
         false, true, '')))[1]::text::bigint AS n
FROM information_schema.tables
WHERE table_schema NOT IN ('pg_catalog','information_schema') AND table_type='BASE TABLE'
ORDER BY 1;
"
psql "${LOCAL_DSN}" -At -F'|' -c "${COUNT_SQL}" | sort > "${WORKDIR}/local_counts.txt"
psql "${CLOUD_DSN}" -At -F'|' -c "${COUNT_SQL}" | sort > "${WORKDIR}/cloud_counts.txt"

echo
printf "%-45s %12s %12s   %s\n" "TABLE" "LOCAL" "CLOUD" "STATUS"
printf '%.0s-' {1..90}; echo
MISMATCH=0
join -t'|' -a1 -a2 -e MISSING -o '0,1.2,2.2' \
  "${WORKDIR}/local_counts.txt" "${WORKDIR}/cloud_counts.txt" \
| while IFS='|' read -r tbl l c; do
    if [[ "$l" == "$c" ]]; then status="ok"; else status="*** MISMATCH ***"; fi
    printf "%-45s %12s %12s   %s\n" "$tbl" "$l" "$c" "$status"
  done

# Recompute mismatch for exit status (the while-subshell above can't set parent vars).
if ! diff -q "${WORKDIR}/local_counts.txt" "${WORKDIR}/cloud_counts.txt" >/dev/null; then
  echo
  echo "==> Row counts differ. Review the table above before trusting the cloud DB."
  echo "    Dump retained at: ${DUMP}"
  exit 2
fi

echo
echo "==> All table row counts match. Migration verified."
echo "    KEEP your local DB as a fallback for at least a few days (do not drop it)."
echo "    Dump retained at: ${DUMP}"
