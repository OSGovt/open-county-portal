# Utopia County demonstration, packaged for Cloudflare Containers.
#
# Everything is built into the image: the portal, a PostgreSQL server, and a
# database already holding the generated county. A container starts in seconds,
# and whatever visitors change disappears when it goes to sleep, so the demo
# always returns to the same clean state. Built by `npx wrangler deploy` from
# deploy/cloudflare (the build context is the project folder).
FROM python:3.12-slim-bookworm

ARG SITE_URL=https://utopia.osgovt.com
ARG DEMO_SCALE=200000
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PGDATA=/var/lib/postgresql/demo PGBIN=/usr/lib/postgresql/16/bin \
    PORTAL_DATA_DIR=/data \
    PORTAL_DATABASE_URL=postgresql+psycopg://portal@/portal?host=/run/postgresql \
    PORTAL_DEMO_MODE=1 \
    PORTAL_SITE_URL=$SITE_URL BUILT_SITE_URL=$SITE_URL

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && install -d /usr/share/keyrings \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-16 fonts-dejavu-core \
 && apt-get purge -y gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 portal \
 && install -d -o portal -g portal /data \
 && install -d -o postgres -g postgres /run/postgresql "$PGDATA"

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY portal ./portal
COPY docs ./docs
COPY deploy ./deploy
COPY tests ./tests
COPY conformance/run.py conformance/README.md conformance/package.json conformance/requirements.txt ./conformance/
COPY Dockerfile docker-compose.yml render.yaml requirements.txt requirements-dev.txt VERSION LICENSE README.md CHANGELOG.md .env.example ./

# Build the demonstration database into the image (about a minute).
RUN install -d -o postgres -g postgres /run/postgresql \
 && runuser -u postgres -- "$PGBIN/initdb" -D "$PGDATA" -A trust -U postgres --encoding=UTF8 --locale=C.UTF-8 --no-sync >/dev/null \
 && runuser -u postgres -- "$PGBIN/pg_ctl" -D "$PGDATA" -o "-c listen_addresses='' -k /run/postgresql -c fsync=off -c wal_level=minimal -c max_wal_senders=0 -c max_wal_size=64MB -c min_wal_size=32MB" -w start \
 && runuser -u postgres -- "$PGBIN/psql" -h /run/postgresql -U postgres -q -c "CREATE ROLE portal LOGIN" -c "CREATE DATABASE portal OWNER portal" \
 && runuser -u portal -- env PORTAL_SECRET_KEY=build python -m portal.cli setup --name "Utopia County" --type county --state zn --state-name Nirvana \
 && runuser -u portal -- env PORTAL_SECRET_KEY=build python -m portal.cli demo --scale "$DEMO_SCALE" \
 && runuser -u portal -- env PORTAL_SECRET_KEY=build python -m portal.cli demo-staff \
 && runuser -u portal -- env PORTAL_SECRET_KEY=build python -m portal.cli export-bulk \
 && runuser -u postgres -- "$PGBIN/psql" -h /run/postgresql -U postgres -q -c "CHECKPOINT" \
 && runuser -u postgres -- "$PGBIN/pg_ctl" -D "$PGDATA" -m fast -w stop

COPY deploy/cloudflare/entrypoint.sh /entrypoint.sh
EXPOSE 8000
CMD ["/entrypoint.sh"]
