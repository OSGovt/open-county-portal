"""Runtime settings, read from environment variables.

Everything an administrator changes day to day (site name, colors, fees,
pages) lives in the database and is edited in the staff console. This file
only holds what the server needs before it can reach the database.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret_key: str
    data_dir: Path
    site_url: str
    environment: str
    secure_cookies: bool
    session_max_age: int
    staff_session_max_age: int
    api_rate_per_minute: int
    api_rate_per_minute_keyed: int
    upload_max_mb: int
    id_upload_retention_days: int

    @property
    def images_dir(self) -> Path:
        return self.data_dir / "images"

    @property
    def cache_dir(self) -> Path:
        return self.data_dir / "cache"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def files_dir(self) -> Path:
        return self.data_dir / "files"

    @property
    def bulk_dir(self) -> Path:
        return self.data_dir / "bulk"

    @property
    def backups_dir(self) -> Path:
        return self.data_dir / "backups"

    @property
    def migration_dir(self) -> Path:
        return self.data_dir / "migration"

    def ensure_dirs(self) -> None:
        for d in (self.images_dir, self.cache_dir, self.uploads_dir, self.files_dir,
                  self.bulk_dir, self.backups_dir, self.migration_dir):
            d.mkdir(parents=True, exist_ok=True)


def load_settings() -> Settings:
    secret = os.environ.get("PORTAL_SECRET_KEY", "")
    env = os.environ.get("PORTAL_ENV", "production")
    if not secret:
        if env == "production":
            raise RuntimeError(
                "PORTAL_SECRET_KEY is not set. The installer writes it to /opt/county-portal/.env; "
                "run 'countyctl doctor' to check the installation."
            )
        secret = "development-only-secret-key-do-not-use-in-production"
    return Settings(
        database_url=os.environ.get("PORTAL_DATABASE_URL", "postgresql+psycopg://portal@localhost/portal"),
        secret_key=secret,
        data_dir=Path(os.environ.get("PORTAL_DATA_DIR", "/var/lib/county-portal/data")),
        site_url=os.environ.get("PORTAL_SITE_URL", "http://localhost:8000").rstrip("/"),
        environment=env,
        secure_cookies=_bool(os.environ.get("PORTAL_SECURE_COOKIES"), default=(env == "production")),
        session_max_age=int(os.environ.get("PORTAL_SESSION_MAX_AGE", str(60 * 60 * 24))),
        staff_session_max_age=int(os.environ.get("PORTAL_STAFF_SESSION_MAX_AGE", str(60 * 60 * 10))),
        api_rate_per_minute=int(os.environ.get("PORTAL_API_RATE", "120")),
        api_rate_per_minute_keyed=int(os.environ.get("PORTAL_API_RATE_KEYED", "1200")),
        upload_max_mb=int(os.environ.get("PORTAL_UPLOAD_MAX_MB", "15")),
        id_upload_retention_days=int(os.environ.get("PORTAL_ID_RETENTION_DAYS", "30")),
    )


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


def reset_settings_cache() -> None:
    global _settings
    _settings = None
