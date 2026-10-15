#!/bin/sh
# Start the built-in database, then the portal. Runs as root; drops to the
# postgres and portal users.
set -e
log() { echo "entrypoint: $*"; }
# If any step fails, print what's needed to diagnose it (it lands in the
# Cloudflare dashboard's logs): the database log and the file permissions.
# shellcheck disable=SC2154  # status is set inside the trap itself
trap 'status=$?; if [ "$status" -ne 0 ]; then
  log "failed with exit code $status"
  [ -f /tmp/postgres.log ] && sed "s/^/postgres log: /" /tmp/postgres.log
  log "running as: $(id)"; ls -ld "$PGDATA" /run/postgresql /data /dev/shm 2>&1 | sed "s/^/entrypoint: /"
  df -h / /tmp 2>&1 | sed "s/^/entrypoint: /"
fi' EXIT

log "starting the database"
install -d -o postgres -g postgres /run/postgresql   # /run may be empty at start
# dynamic_shared_memory_type=mmap: some container hosts have no /dev/shm.
runuser -u postgres -- "$PGBIN/pg_ctl" -D "$PGDATA" -l /tmp/postgres.log \
  -o "-c listen_addresses='' -k /run/postgresql -c fsync=off -c shared_buffers=256MB -c dynamic_shared_memory_type=mmap -c wal_level=minimal -c max_wal_senders=0 -c max_wal_size=64MB -c min_wal_size=32MB" -w start

log "database started"

# A fresh signing key each start: sessions end when the demo resets anyway.
PORTAL_SECRET_KEY="${PORTAL_SECRET_KEY:-$(python -c 'import secrets; print(secrets.token_hex(32))')}"
export PORTAL_SECRET_KEY

# Open data files and the catalog carry the site address; rebuild them if it changed.
if [ "${PORTAL_SITE_URL:-}" != "${BUILT_SITE_URL:-}" ]; then
  (sleep 15; runuser -u portal -- python -m portal.cli export-bulk >/tmp/export-bulk.log 2>&1) &
fi

log "starting the portal on port 8000"
exec runuser -u portal -- uvicorn 'portal.app:create_app' --factory --host 0.0.0.0 --port 8000 \
  --workers "${PORTAL_WORKERS:-2}" --proxy-headers --forwarded-allow-ips='*'
