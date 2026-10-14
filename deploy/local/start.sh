#!/usr/bin/env bash
# Start the Utopia County demonstration on this computer: http://localhost:8080
# Needs Docker (Docker Desktop on Windows or Mac, with WSL on Windows).
# Safe to run again: it keeps the same passwords and data.
set -euo pipefail
cd "$(dirname "$0")"

command -v docker >/dev/null || { echo "Docker isn't installed or isn't running. See docs/admin/hosted-demo.md, part 1."; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker is installed but not running. Start Docker Desktop and try again."; exit 1; }

if [ ! -f .env ]; then
  umask 077
  {
    echo "POSTGRES_PASSWORD=$(openssl rand -hex 24 2>/dev/null || head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    echo "PORTAL_SECRET_KEY=$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
    echo "ADMIN_EMAIL=${ADMIN_EMAIL:-admin@example.com}"
    echo "DEMO_SCALE=${DEMO_SCALE:-200000}"
  } > .env
fi

echo "Building and starting (the first time takes 5 to 10 minutes)..."
docker compose up -d --build

echo "Waiting for the portal and the demonstration county (about a minute or two the first time)..."
for i in $(seq 1 120); do
  if curl -fs http://localhost:8080/healthz >/dev/null 2>&1; then break; fi
  sleep 5
  [ "$i" -eq 120 ] && { echo "It didn't start. See: docker compose -f deploy/local/docker-compose.yml logs app"; exit 1; }
done

echo
echo "Open County Portal is running: http://localhost:8080"
echo "Staff console:                 http://localhost:8080/staff"
docker compose logs app 2>/dev/null | grep -E "Email:|Temporary password:" | tail -2 || true
echo
echo "Stop it:          docker compose -f deploy/local/docker-compose.yml stop"
echo "Start it again:   ./deploy/local/start.sh"
echo "Erase everything: docker compose -f deploy/local/docker-compose.yml down -v && rm deploy/local/.env"
