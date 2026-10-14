#!/usr/bin/env bash
# Open County Portal installer.
#
# Run on a fresh Ubuntu 24.04 / 22.04 or Debian 12 server, from a copy of the
# project (a git clone or an unpacked release):
#
#   sudo ./deploy/install.sh
#
# It asks six questions, installs Docker, builds the portal, starts it, takes
# the first backup and prints the first administrator's sign-in. Running it
# again is safe: it keeps your settings and data and only fills in what's missing.
#
# Unattended install: set the answers as environment variables first, e.g.
#   sudo PORTAL_NAME="Example County" PORTAL_TYPE=county PORTAL_STATE=tx \
#        PORTAL_HOST=portal.example-county.gov PORTAL_TLS_MODE=public \
#        PORTAL_ADMIN_EMAIL=it@example-county.gov PORTAL_ADMIN_NAME="Pat Lee" \
#        ./deploy/install.sh --yes
set -Eeuo pipefail

INSTALL_DIR="/opt/county-portal"
DATA_ROOT="/var/lib/county-portal"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ASSUME_YES=0
[ "${1:-}" = "--yes" ] && ASSUME_YES=1

step=0
STEPS=10
say()  { printf '%s\n' "$*"; }
section() { step=$((step+1)); printf '\n\033[1m[%d/%d] %s\033[0m\n' "$step" "$STEPS" "$*"; }
die()  { printf '\n\033[1mInstall stopped:\033[0m %s\n' "$*" >&2; printf 'Nothing is half-finished that a re-run will not fix. After fixing the problem, run the installer again.\n' >&2; exit 1; }
trap 'die "an unexpected error on line $LINENO. The output above shows what failed."' ERR

ask() {
  # ask VAR "Question" "default"
  local var="$1" q="$2" def="${3:-}" ans
  if [ -n "${!var:-}" ]; then return; fi
  if [ "$ASSUME_YES" -eq 1 ]; then
    [ -n "$def" ] || die "$var must be set for an unattended install."
    printf -v "$var" '%s' "$def"; return
  fi
  if [ -n "$def" ]; then read -r -p "$q [$def]: " ans; else read -r -p "$q: " ans; fi
  ans="${ans:-$def}"
  [ -n "$ans" ] || { say "An answer is needed."; ask "$var" "$q" "$def"; return; }
  printf -v "$var" '%s' "$ans"
}

# ---------------------------------------------------------------------------
section "Checking this server"
[ "$(id -u)" -eq 0 ] || die "run the installer with sudo:  sudo ./deploy/install.sh"
[ -f "$SRC_DIR/VERSION" ] && [ -f "$SRC_DIR/docker-compose.yml" ] || die "run this from inside the Open County Portal folder."
. /etc/os-release
case "$ID:${VERSION_ID:-}" in
  ubuntu:24.04|ubuntu:22.04|debian:12) say "  Operating system: $PRETTY_NAME (supported)" ;;
  *) say "  Operating system: $PRETTY_NAME. This installer is tested on Ubuntu 24.04/22.04 and Debian 12; it may still work."
     [ "$ASSUME_YES" -eq 1 ] || { read -r -p "  Continue anyway? (y/N) " c; [ "$c" = y ] || [ "$c" = Y ] || die "stopped at your request."; } ;;
esac
cpus="$(nproc)"; mem_gb="$(awk '/MemTotal/ {print int($2/1048576+0.5)}' /proc/meminfo)"
mkdir -p "$DATA_ROOT"
disk_gb="$(df -Pk "$DATA_ROOT" | awk 'NR==2 {print int($4/1048576)}')"
say "  CPUs: $cpus   Memory: ${mem_gb} GB   Free disk for data: ${disk_gb} GB"
[ "$mem_gb" -ge 3 ] || die "the server needs at least 4 GB of memory (8 GB recommended)."
[ "$disk_gb" -ge 20 ] || die "at least 20 GB of free disk is needed under $DATA_ROOT, plus room for your record images (see docs/admin/sizing.md)."
[ "$cpus" -ge 2 ] || say "  Note: 2 or more CPUs are recommended."
for port in 80 443; do
  if ss -ltnH "sport = :$port" 2>/dev/null | grep -q . && ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q '^county-portal-web'; then
    die "something else on this server is already using port $port. Stop it (often Apache or nginx: sudo systemctl disable --now apache2 nginx) and re-run."
  fi
done

# ---------------------------------------------------------------------------
section "Six questions about your site"
if [ -f "$INSTALL_DIR/.env" ]; then
  say "  Settings already exist in $INSTALL_DIR/.env; keeping them."
  # shellcheck disable=SC1090
  PORTAL_HOST="$(sed -n 's/^PORTAL_HOST=//p' "$INSTALL_DIR/.env")"
  PORTAL_TLS_MODE="$(sed -n 's/^PORTAL_TLS_MODE=//p' "$INSTALL_DIR/.env")"
  PORTAL_ADMIN_EMAIL="$(sed -n 's/^PORTAL_ADMIN_EMAIL=//p' "$INSTALL_DIR/.env")"
  FRESH=0
  if [ -f "$INSTALL_DIR/.install-answers" ]; then
    # shellcheck disable=SC1091
    . "$INSTALL_DIR/.install-answers"
  fi
else
  FRESH=1
  say "  Press Enter to accept a suggestion in [brackets]."
  ask PORTAL_NAME  "1. Name of your government as residents know it (e.g. Example County)" ""
  say "     Types: county, municipality, special_district, school_district"
  ask PORTAL_TYPE  "2. Type of government" "county"
  case "$PORTAL_TYPE" in county|municipality|special_district|school_district) ;; *) die "type must be one of: county, municipality, special_district, school_district";; esac
  ask PORTAL_STATE "3. Two-letter state (e.g. tx)" ""
  PORTAL_STATE="$(printf '%s' "$PORTAL_STATE" | tr 'A-Z' 'a-z')"
  if [ -f "$SRC_DIR/portal/statepacks/$PORTAL_STATE/pack.yaml" ]; then
    PACK="$PORTAL_STATE"; STATE_NAME=""
    say "     A state pack for '$PORTAL_STATE' is included."
  else
    PACK="_template"
    say "     There's no state pack for '$PORTAL_STATE' yet. The site will start with no offices, services or fees;"
    say "     you add them in the staff console (or write a pack: docs/state-packs/writing-a-state-pack.md)."
    ask STATE_NAME "     Full state name to show on the site (e.g. Ohio)" ""
  fi
  ask PORTAL_HOST  "4. Web address for the portal, without https:// (e.g. portal.example-county.gov)" ""
  PORTAL_HOST="${PORTAL_HOST#https://}"; PORTAL_HOST="${PORTAL_HOST#http://}"; PORTAL_HOST="${PORTAL_HOST%%/*}"
  say "     HTTPS certificate:"
  say "       public   - free automatic certificate (the address must point here in public DNS, ports 80+443 open)"
  say "       internal - for a test server or inside the county network only (browsers warn until trusted)"
  say "       provided - your organization's own certificate files (see docs/admin/https.md)"
  ask PORTAL_TLS_MODE "5. Certificate type" "public"
  case "$PORTAL_TLS_MODE" in public|internal|provided) ;; *) die "certificate type must be public, internal or provided";; esac
  ask PORTAL_ADMIN_EMAIL "6. Your email (first administrator; also used for certificate notices)" ""
  ask PORTAL_ADMIN_NAME  "   Your name" "Administrator"
  say ""
  say "  Name: $PORTAL_NAME ($PORTAL_TYPE, $PORTAL_STATE)"
  say "  Address: https://$PORTAL_HOST  (certificate: $PORTAL_TLS_MODE)"
  say "  First administrator: $PORTAL_ADMIN_NAME <$PORTAL_ADMIN_EMAIL>"
  if [ "$ASSUME_YES" -ne 1 ]; then read -r -p "  Is this right? (Y/n) " c; [ "${c:-Y}" = Y ] || [ "${c:-Y}" = y ] || die "stopped; run again to re-answer."; fi
fi
if [ "$PORTAL_TLS_MODE" = provided ] && { [ ! -f "$DATA_ROOT/caddy/certs/portal.crt" ] || [ ! -f "$DATA_ROOT/caddy/certs/portal.key" ]; }; then
  mkdir -p "$DATA_ROOT/caddy/certs"
  die "for 'provided' certificates, copy your certificate (full chain) to $DATA_ROOT/caddy/certs/portal.crt and the key to $DATA_ROOT/caddy/certs/portal.key, then re-run."
fi

# ---------------------------------------------------------------------------
section "Installing system packages and Docker"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq ca-certificates curl git rsync gnupg openssl >/dev/null
if ! command -v docker >/dev/null 2>&1 || ! docker compose version >/dev/null 2>&1; then
  say "  Installing Docker from Docker's official repository..."
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/$ID/gpg" -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/$ID ${VERSION_CODENAME} stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -qq
  apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin >/dev/null
fi
systemctl enable --now docker >/dev/null
say "  $(docker --version)"
say "  $(docker compose version)"
timedatectl set-ntp true 2>/dev/null || true

# ---------------------------------------------------------------------------
section "Copying the portal to $INSTALL_DIR"
if [ "$SRC_DIR" != "$INSTALL_DIR" ]; then
  mkdir -p "$INSTALL_DIR"
  rsync -a --exclude .env --exclude '__pycache__' "$SRC_DIR/" "$INSTALL_DIR/"
fi
if [ -d "$INSTALL_DIR/.git" ]; then
  git config --global --add safe.directory "$INSTALL_DIR" 2>/dev/null || true
fi
ln -sf "$INSTALL_DIR/deploy/countyctl" /usr/local/bin/countyctl
chmod +x "$INSTALL_DIR/deploy/countyctl"
say "  Version $(cat "$INSTALL_DIR/VERSION"). The 'countyctl' command is installed."

# ---------------------------------------------------------------------------
section "Creating data folders and settings"
mkdir -p "$DATA_ROOT"/{data,postgres,caddy,import,releases}
chown -R 1000:1000 "$DATA_ROOT/data"
chmod 755 "$DATA_ROOT/import"
touch /var/log/county-portal.log
if [ "$FRESH" -eq 1 ]; then
  umask 077
  cat > "$INSTALL_DIR/.env" <<EOF
# Open County Portal settings. Written by the installer on $(date -I).
# After changing anything here, run: sudo countyctl restart
# Keep this file private: it holds passwords. It is backed up only by you.

# --- Site ---
PORTAL_HOST=$PORTAL_HOST
PORTAL_SITE_URL=https://$PORTAL_HOST
PORTAL_TLS_MODE=$PORTAL_TLS_MODE
PORTAL_ADMIN_EMAIL=$PORTAL_ADMIN_EMAIL
PORTAL_ENV=production

# --- Secrets (generated; do not share or change after go-live) ---
PORTAL_SECRET_KEY=$(openssl rand -hex 32)
POSTGRES_PASSWORD=$(openssl rand -hex 24)

# --- Outgoing email for receipts and notices (see docs/admin/email.md) ---
PORTAL_SMTP_HOST=
PORTAL_SMTP_PORT=587
PORTAL_SMTP_USER=
PORTAL_SMTP_PASSWORD=
PORTAL_SMTP_FROM=
PORTAL_SMTP_STARTTLS=true

# --- Backups (see docs/admin/backups.md) ---
# Command that copies each backup off this server; {path} is the backup folder.
# Example: PORTAL_BACKUP_COPY_CMD=rsync -a {path} backup@nas.example-county.gov:/portal-backups/
PORTAL_BACKUP_COPY_CMD=
PORTAL_BACKUP_KEEP=14

# --- Tuning (defaults are fine for most sites) ---
PORTAL_WORKERS=4
PORTAL_API_RATE=120
PORTAL_API_RATE_KEYED=1200
PORTAL_UPLOAD_MAX_MB=15
PORTAL_ID_RETENTION_DAYS=30
EOF
  umask 022
  chmod 600 "$INSTALL_DIR/.env"
  say "  Settings written to $INSTALL_DIR/.env (private; passwords generated)."
  {
    printf 'PORTAL_NAME=%q\nPORTAL_TYPE=%q\nPORTAL_STATE=%q\nPACK=%q\nSTATE_NAME=%q\nPORTAL_ADMIN_NAME=%q\n' \
      "$PORTAL_NAME" "$PORTAL_TYPE" "$PORTAL_STATE" "$PACK" "${STATE_NAME:-}" "$PORTAL_ADMIN_NAME"
  } > "$INSTALL_DIR/.install-answers"
  chmod 600 "$INSTALL_DIR/.install-answers"
fi

# ---------------------------------------------------------------------------
section "Scheduling nightly backups and maintenance"
cat > /etc/systemd/system/county-portal-nightly.service <<'EOF'
[Unit]
Description=Open County Portal nightly backup and maintenance
After=docker.service
Requires=docker.service

[Service]
Type=oneshot
ExecStart=/usr/local/bin/countyctl nightly
EOF
cat > /etc/systemd/system/county-portal-nightly.timer <<'EOF'
[Unit]
Description=Run Open County Portal nightly maintenance at about 2:30 a.m.

[Timer]
OnCalendar=*-*-* 02:30:00
RandomizedDelaySec=15m
Persistent=true

[Install]
WantedBy=timers.target
EOF
cat > /etc/logrotate.d/county-portal <<'EOF'
/var/log/county-portal.log {
  monthly
  rotate 24
  compress
  missingok
  notifempty
}
EOF
systemctl daemon-reload
systemctl enable --now county-portal-nightly.timer >/dev/null
say "  Backup, open-data export, text reading and upload cleanup run every night."
if command -v ufw >/dev/null && ufw status | grep -q "Status: active"; then
  ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null
  say "  Firewall (ufw): opened ports 80 and 443."
fi

# ---------------------------------------------------------------------------
section "Building the portal (first time takes 5-10 minutes)"
cd "$INSTALL_DIR"
docker compose pull db web
docker compose build app

# ---------------------------------------------------------------------------
section "Starting the portal"
docker compose up -d
for i in $(seq 1 60); do
  if docker compose exec -T app python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).status == 200 else 1)" >/dev/null 2>&1; then
    break
  fi
  [ "$i" -eq 60 ] && die "the portal didn't start. See: sudo countyctl logs app"
  sleep 3
done
say "  The portal is running."

# ---------------------------------------------------------------------------
section "Setting up your site"
staff_count="$(docker compose exec -T app python -m portal.cli check 2>/dev/null | sed -n 's/.*, \([0-9]*\) staff account.*/\1/p')"
if [ "${staff_count:-0}" = 0 ] && [ -n "${PORTAL_NAME:-}" ]; then
  args=(setup --name "$PORTAL_NAME" --type "$PORTAL_TYPE" --state "$PACK" --admin-email "$PORTAL_ADMIN_EMAIL" --admin-name "$PORTAL_ADMIN_NAME")
  [ -n "${STATE_NAME:-}" ] && args+=(--state-name "$STATE_NAME")
  docker compose exec -T app python -m portal.cli "${args[@]}"
else
  docker compose exec -T app python -m portal.cli setup
fi

# ---------------------------------------------------------------------------
section "Taking the first backup"
/usr/local/bin/countyctl backup

say ""
printf '\033[1mInstalled.\033[0m\n'
say ""
say "Sign in to the staff console:  https://$PORTAL_HOST/staff"
if [ -f "$DATA_ROOT/data/status/first-admin.txt" ]; then
  sed 's/^/  /' "$DATA_ROOT/data/status/first-admin.txt"
fi
say ""
say "Next steps (all in docs/admin/README.md, also under Help in the staff console):"
say "  1. Sign in, choose your password, and set up the phone code."
say "  2. Run: sudo countyctl doctor"
say "  3. Set up email and off-site backups in $INSTALL_DIR/.env"
say "  4. Style the site: Staff console > Settings > Theme"
say "  5. Move your records and old pages in: docs/admin/migration.md"
if [ "$PORTAL_TLS_MODE" = public ]; then
  say ""
  say "If the address doesn't load yet: point $PORTAL_HOST at this server's public IP in DNS and"
  say "open ports 80 and 443. The certificate is issued automatically within a minute after that."
fi
