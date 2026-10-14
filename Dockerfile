# Open County Portal application image.
# Built on the server by the installer and by 'countyctl update'.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PORTAL_DATA_DIR=/data

# Tools the portal uses:
#   postgresql-client-16  backups and restores (must match the database's major version)
#   tesseract-ocr         machine-readable text from scanned pages
#   poppler-utils         splitting PDF document images into pages
#   fonts-dejavu-core     certification pages on certified copies
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl gnupg \
 && install -d /usr/share/keyrings \
 && curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc | gpg --dearmor -o /usr/share/keyrings/pgdg.gpg \
 && echo "deb [signed-by=/usr/share/keyrings/pgdg.gpg] http://apt.postgresql.org/pub/repos/apt bookworm-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends postgresql-client-16 tesseract-ocr tesseract-ocr-eng poppler-utils fonts-dejavu-core \
 && apt-get purge -y gnupg && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 portal
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY portal ./portal
COPY docs ./docs
# Shipped in the image so /source/download offers the complete source (AGPL section 13).
COPY deploy ./deploy
COPY tests ./tests
COPY conformance/run.py conformance/README.md conformance/package.json conformance/requirements.txt ./conformance/
COPY Dockerfile docker-compose.yml requirements.txt requirements-dev.txt VERSION LICENSE README.md CHANGELOG.md .env.example ./

USER portal
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=300s --retries=3 \
  CMD python -c "import os,urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:%s/healthz' % os.environ.get('PORT', '8000'), timeout=4).status == 200 else 1)"

# Bring the database up to date, then serve. Workers default to 4; set PORTAL_WORKERS in .env to change.
# PORT is set by hosting platforms such as Render; bootstrap does nothing unless PORTAL_BOOTSTRAP_NAME is set.
CMD ["sh", "-c", "python -m portal.cli upgrade-db && python -m portal.cli bootstrap && exec uvicorn 'portal.app:create_app' --factory --host 0.0.0.0 --port ${PORT:-8000} --workers ${PORTAL_WORKERS:-4} --proxy-headers --forwarded-allow-ips='*'"]
