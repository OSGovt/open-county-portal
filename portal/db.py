"""Database schema and connection.

Plain SQLAlchemy Core tables, so the schema reads like a list of what the
portal stores. Every table that the open API publishes has an ``updated_at``
column, and deletions are recorded in ``tombstones`` so the change feed can
tell data users what disappeared.
"""
from __future__ import annotations

import datetime as dt
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import (JSON, BigInteger, Boolean, Column, Date, DateTime, ForeignKey, Index,
                        Integer, MetaData, String, Table, Text, UniqueConstraint, create_engine,
                        func, text)
from sqlalchemy.engine import Connection, Engine

from .settings import get_settings

metadata = MetaData()

SCHEMA_VERSION = 1


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _ts(name: str, **kw) -> Column:
    return Column(name, DateTime(timezone=True), **kw)


def _updated() -> Column:
    return Column("updated_at", DateTime(timezone=True), nullable=False, default=utcnow,
                  onupdate=utcnow, index=True)


schema_info = Table(
    "schema_info", metadata,
    Column("id", Integer, primary_key=True),
    Column("version", Integer, nullable=False),
    _ts("applied_at", nullable=False, default=utcnow),
)

# Key/value settings edited in the staff console (site identity, theme, payment
# policy, alert banner). Every change is copied to setting_history so any
# earlier version can be restored with one click.
settings_table = Table(
    "settings", metadata,
    Column("key", String(100), primary_key=True),
    Column("value", JSON, nullable=False),
    _updated(),
    Column("updated_by", String(200)),
)

setting_history = Table(
    "setting_history", metadata,
    Column("id", Integer, primary_key=True),
    Column("key", String(100), nullable=False, index=True),
    Column("value", JSON, nullable=False),
    _ts("changed_at", nullable=False, default=utcnow),
    Column("changed_by", String(200)),
    Column("note", String(300)),
)

offices = Table(
    "offices", metadata,
    Column("id", Integer, primary_key=True),
    Column("slug", String(80), unique=True, nullable=False),
    Column("name", String(200), nullable=False),
    Column("official", String(200)),
    Column("description", Text),
    Column("phone", String(50)),
    Column("email", String(200)),
    Column("address", Text),
    Column("hours", Text),
    Column("merchant_account", String(200)),
    Column("sort", Integer, default=100),
    Column("active", Boolean, nullable=False, default=True),
    _updated(),
)

services = Table(
    "services", metadata,
    Column("id", Integer, primary_key=True),
    Column("slug", String(120), unique=True, nullable=False),
    Column("office_slug", String(80)),
    Column("title", String(200), nullable=False),
    Column("summary", String(400)),
    Column("who", Text),
    Column("needs", Text),
    Column("cost", Text),
    Column("timing", Text),
    Column("online_label", String(120)),
    Column("online_target", String(500)),
    Column("handoff", Boolean, nullable=False, default=False),
    Column("in_person", Text),
    Column("body", Text),
    Column("featured", Boolean, nullable=False, default=False),
    Column("category", String(80)),
    Column("keywords", String(400)),
    Column("published", Boolean, nullable=False, default=True),
    Column("sort", Integer, default=100),
    _updated(),
)

pages = Table(
    "pages", metadata,
    Column("id", Integer, primary_key=True),
    Column("slug", String(200), unique=True, nullable=False),
    Column("title", String(300), nullable=False),
    Column("body", Text, nullable=False, default=""),
    Column("published", Boolean, nullable=False, default=False),
    Column("source_url", String(1000)),
    Column("review_note", Text),
    _updated(),
)

redirects = Table(
    "redirects", metadata,
    Column("old_path", String(1000), primary_key=True),
    Column("new_path", String(1000), nullable=False),
    _updated(),
)

files = Table(
    "files", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(300), nullable=False),
    Column("path", String(1000), nullable=False),
    Column("mime", String(100)),
    Column("sha256", String(64)),
    Column("bytes", BigInteger),
    Column("source_url", String(1000)),
    Column("needs_accessibility_review", Boolean, nullable=False, default=False),
    _updated(),
)

fees = Table(
    "fees", metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String(80), nullable=False),
    Column("office_slug", String(80), nullable=False),
    Column("label", String(300), nullable=False),
    Column("amount_cents", Integer, nullable=False),
    Column("unit", String(60), nullable=False, default="each"),
    Column("statute", String(300)),
    Column("fund", String(200), nullable=False, default="General Fund"),
    Column("effective_from", Date, nullable=False),
    Column("effective_to", Date),
    Column("adopted_by", String(300)),
    Column("counter", Boolean, nullable=False, default=True),
    Column("confirmed", Boolean, nullable=False, default=False),
    Column("confirmed_by", String(200)),
    _updated(),
    UniqueConstraint("code", "effective_from", name="uq_fee_code_from"),
)

instruments = Table(
    "instruments", metadata,
    Column("id", Integer, primary_key=True),
    Column("instrument_number", String(80), unique=True, nullable=False),
    Column("book", String(40)),
    Column("page", String(40)),
    Column("doc_type", String(120), nullable=False),
    Column("recorded_date", Date),
    Column("legal_description", Text),
    Column("property_id", String(120)),
    Column("page_count", Integer, nullable=False, default=0),
    Column("remarks", Text),
    Column("status", String(20), nullable=False, default="public"),  # public | restricted
    Column("import_batch", Integer, index=True),
    Column("source_hash", String(64)),
    _updated(),
)
Index("ix_instruments_recorded", instruments.c.recorded_date)
Index("ix_instruments_doctype", instruments.c.doc_type)

parties = Table(
    "parties", metadata,
    Column("id", Integer, primary_key=True),
    Column("instrument_id", Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("role", String(20), nullable=False),  # grantor | grantee
    Column("name", String(400), nullable=False),
    Column("name_norm", String(400), nullable=False, index=True),
)

images = Table(
    "images", metadata,
    Column("id", Integer, primary_key=True),
    Column("instrument_id", Integer, ForeignKey("instruments.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("seq", Integer, nullable=False),
    Column("path", String(1000), nullable=False),
    Column("frame", Integer, nullable=False, default=0),
    Column("mime", String(100)),
    Column("sha256", String(64), nullable=False),
    Column("bytes", BigInteger),
    Column("ocr_text", Text),
    Column("redacted", Boolean, nullable=False, default=False),
    _updated(),
    UniqueConstraint("instrument_id", "seq", name="uq_image_seq"),
)

redaction_requests = Table(
    "redaction_requests", metadata,
    Column("id", Integer, primary_key=True),
    Column("number", String(40), unique=True, nullable=False),
    Column("requester_name", String(300), nullable=False),
    Column("category", String(200), nullable=False),
    Column("email", String(300)),
    Column("phone", String(60)),
    Column("search_names", Text),
    Column("details", Text),
    Column("status", String(30), nullable=False, default="received"),  # received | approved | denied | applied | rescinded
    _ts("received_at", nullable=False, default=utcnow),
    _ts("decided_at"),
    Column("decided_by", String(200)),
    Column("notes", Text),
)

redaction_marks = Table(
    "redaction_marks", metadata,
    Column("id", Integer, primary_key=True),
    Column("image_id", Integer, ForeignKey("images.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("request_id", Integer, ForeignKey("redaction_requests.id", ondelete="SET NULL")),
    Column("x", Integer, nullable=False),  # per-mille of width/height, 0..1000
    Column("y", Integer, nullable=False),
    Column("w", Integer, nullable=False),
    Column("h", Integer, nullable=False),
    Column("reason", String(300), nullable=False),
    Column("created_by", String(200)),
    _ts("created_at", nullable=False, default=utcnow),
)

meetings = Table(
    "meetings", metadata,
    Column("id", Integer, primary_key=True),
    Column("body", String(200), nullable=False),
    Column("title", String(300), nullable=False),
    _ts("starts_at", nullable=False),
    Column("location", String(400)),
    Column("agenda", Text),
    _ts("posted_at"),
    Column("video_url", String(1000)),
    Column("minutes", Text),
    Column("status", String(30), nullable=False, default="draft"),  # draft | posted | held | cancelled
    _updated(),
)

postings = Table(
    "postings", metadata,
    Column("id", Integer, primary_key=True),
    Column("rule_code", String(80), index=True),
    Column("title", String(300), nullable=False),
    Column("body", Text),
    Column("office_slug", String(80)),
    Column("file_id", Integer, ForeignKey("files.id", ondelete="SET NULL")),
    _ts("posted_at", nullable=False, default=utcnow),
    Column("remove_after", Date),
    Column("published", Boolean, nullable=False, default=True),
    _updated(),
)

pia_requests = Table(
    "pia_requests", metadata,
    Column("id", Integer, primary_key=True),
    Column("number", String(40), unique=True, nullable=False),
    Column("office_slug", String(80)),
    Column("description", Text, nullable=False),
    Column("delivery", String(40), nullable=False),
    Column("name", String(300)),
    Column("email", String(300)),
    Column("phone", String(60)),
    Column("status", String(30), nullable=False, default="received"),  # received | clarification | estimate | ruling | released | closed
    _ts("received_at", nullable=False, default=utcnow),
    Column("staff_notes", Text),
    Column("response", Text),
    Column("publish_response", Boolean, nullable=False, default=False),
    _updated(),
)

applications = Table(
    "applications", metadata,
    Column("id", Integer, primary_key=True),
    Column("number", String(40), unique=True, nullable=False),
    Column("form", String(80), nullable=False, index=True),
    Column("office_slug", String(80)),
    Column("data", JSON, nullable=False),
    Column("uploads", JSON, nullable=False, default=list),
    Column("email", String(300)),
    Column("status", String(30), nullable=False, default="received"),
    Column("order_id", Integer),
    _ts("created_at", nullable=False, default=utcnow),
    Column("staff_notes", Text),
    _updated(),
)

receivables = Table(
    "receivables", metadata,
    Column("id", Integer, primary_key=True),
    Column("kind", String(40), nullable=False),  # property_tax | court | utility | permit | other
    Column("office_slug", String(80), nullable=False),
    Column("account", String(120), nullable=False),
    Column("name", String(400)),
    Column("description", String(500)),
    Column("address", String(500)),
    Column("amount_due_cents", Integer, nullable=False),
    Column("due_date", Date),
    Column("allow_partial", Boolean, nullable=False, default=True),
    Column("fee_code", String(80)),
    Column("import_batch", Integer, index=True),
    _updated(),
    UniqueConstraint("kind", "account", name="uq_receivable_kind_account"),
)

orders = Table(
    "orders", metadata,
    Column("id", Integer, primary_key=True),
    Column("number", String(40), unique=True, nullable=False),
    Column("token", String(64), nullable=False),
    Column("channel", String(20), nullable=False),  # online | counter
    Column("status", String(20), nullable=False, default="pending"),  # pending | paid | failed | cancelled | refunded | void
    Column("email", String(300)),
    Column("reference", String(300)),
    Column("subtotal_cents", Integer, nullable=False, default=0),
    Column("fee_cents", Integer, nullable=False, default=0),
    Column("total_cents", Integer, nullable=False, default=0),
    Column("method", String(30)),
    Column("processor", String(60)),
    Column("processor_ref", String(200)),
    Column("drawer_session_id", Integer),
    Column("staff_user", String(200)),
    _ts("created_at", nullable=False, default=utcnow),
    _ts("paid_at"),
    _updated(),
)

order_lines = Table(
    "order_lines", metadata,
    Column("id", Integer, primary_key=True),
    Column("order_id", Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("office_slug", String(80), nullable=False),
    Column("kind", String(40), nullable=False),  # fee | receivable | certified_copy
    Column("fee_code", String(80)),
    Column("label", String(500), nullable=False),
    Column("qty", Integer, nullable=False, default=1),
    Column("unit_cents", Integer, nullable=False),
    Column("amount_cents", Integer, nullable=False),
    Column("statute", String(300)),
    Column("fund", String(200)),
    Column("ref", String(300)),
    Column("fulfil_status", String(30), nullable=False, default="none"),  # none | pending | done
)

tenders = Table(
    "tenders", metadata,
    Column("id", Integer, primary_key=True),
    Column("order_id", Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True),
    Column("kind", String(20), nullable=False),  # card | cash | check | escrow | ach | wallet
    Column("amount_cents", Integer, nullable=False),
    Column("detail", String(300)),
    _ts("created_at", nullable=False, default=utcnow),
)

escrow_accounts = Table(
    "escrow_accounts", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(300), nullable=False),
    Column("email", String(300)),
    Column("balance_cents", Integer, nullable=False, default=0),
    Column("active", Boolean, nullable=False, default=True),
    _updated(),
)

escrow_ledger = Table(
    "escrow_ledger", metadata,
    Column("id", Integer, primary_key=True),
    Column("account_id", Integer, ForeignKey("escrow_accounts.id"), nullable=False, index=True),
    Column("amount_cents", Integer, nullable=False),
    Column("order_id", Integer),
    Column("note", String(300)),
    Column("by_user", String(200)),
    _ts("at", nullable=False, default=utcnow),
)

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("email", String(300), unique=True, nullable=False),
    Column("name", String(300), nullable=False),
    Column("password_hash", String(300), nullable=False),
    Column("totp_secret", String(64)),
    Column("mfa_enrolled", Boolean, nullable=False, default=False),
    Column("roles", JSON, nullable=False, default=list),
    Column("offices", JSON, nullable=False, default=list),
    Column("must_change_password", Boolean, nullable=False, default=True),
    Column("active", Boolean, nullable=False, default=True),
    Column("failed_logins", Integer, nullable=False, default=0),
    _ts("locked_until"),
    _ts("last_login"),
    _ts("created_at", nullable=False, default=utcnow),
)

drawers = Table(
    "drawers", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(120), nullable=False),
    Column("office_slug", String(80), nullable=False),
    Column("active", Boolean, nullable=False, default=True),
)

drawer_sessions = Table(
    "drawer_sessions", metadata,
    Column("id", Integer, primary_key=True),
    Column("drawer_id", Integer, ForeignKey("drawers.id"), nullable=False, index=True),
    Column("opened_by", String(200), nullable=False),
    _ts("opened_at", nullable=False, default=utcnow),
    Column("opening_cash_cents", Integer, nullable=False, default=0),
    Column("closed_by", String(200)),
    _ts("closed_at"),
    Column("counted_cash_cents", Integer),
    Column("expected_cash_cents", Integer),
    Column("variance_cents", Integer),
    Column("close_note", Text),
)

# Electronic certified copies: each issued PDF gets a verification code and
# its SHA-256, so anyone can confirm at /verify/<code> that a copy is genuine
# and unaltered.
certified_copies = Table(
    "certified_copies", metadata,
    Column("id", Integer, primary_key=True),
    Column("code", String(40), unique=True, nullable=False),
    Column("order_line_id", Integer, ForeignKey("order_lines.id", ondelete="SET NULL")),
    Column("instrument_number", String(80), nullable=False),
    Column("file_id", Integer, ForeignKey("files.id", ondelete="SET NULL")),
    Column("sha256", String(64), nullable=False),
    Column("issued_by", String(200), nullable=False),
    _ts("issued_at", nullable=False, default=utcnow),
    Column("revoked", Boolean, nullable=False, default=False),
)

api_keys = Table(
    "api_keys", metadata,
    Column("id", Integer, primary_key=True),
    Column("key_hash", String(64), unique=True, nullable=False),
    Column("label", String(200), nullable=False),
    Column("email", String(300)),
    Column("active", Boolean, nullable=False, default=True),
    _ts("created_at", nullable=False, default=utcnow),
)

import_batches = Table(
    "import_batches", metadata,
    Column("id", Integer, primary_key=True),
    Column("kind", String(40), nullable=False),
    Column("source", String(1000)),
    Column("mapping", JSON),
    _ts("started_at", nullable=False, default=utcnow),
    _ts("finished_at"),
    Column("rows_in", Integer, default=0),
    Column("rows_loaded", Integer, default=0),
    Column("rows_rejected", Integer, default=0),
    Column("status", String(30), nullable=False, default="running"),  # running | loaded | verified | undone | failed
    Column("report_path", String(1000)),
    Column("signed_off_by", String(300)),
)

audit_log = Table(
    "audit_log", metadata,
    Column("id", BigInteger, primary_key=True),
    _ts("at", nullable=False, default=utcnow, index=True),
    Column("actor", String(200)),
    Column("action", String(120), nullable=False),
    Column("object_type", String(80)),
    Column("object_id", String(120)),
    Column("detail", JSON),
    Column("ip", String(80)),
)

tombstones = Table(
    "tombstones", metadata,
    Column("id", Integer, primary_key=True),
    Column("object_type", String(80), nullable=False),
    Column("object_id", String(120), nullable=False),
    _ts("deleted_at", nullable=False, default=utcnow, index=True),
)

sequences = Table(
    "number_sequences", metadata,
    Column("name", String(60), primary_key=True),
    Column("value", Integer, nullable=False),
)

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(get_settings().database_url, pool_pre_ping=True, future=True)
    return _engine


def reset_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


@contextmanager
def tx() -> Iterator[Connection]:
    """A transaction: commits on success, rolls back on any error."""
    with get_engine().begin() as conn:
        yield conn


def next_number(conn: Connection, name: str, prefix: str) -> str:
    """Human-friendly sequential numbers such as PIR-2026-0007."""
    year = utcnow().year
    key = f"{name}-{year}"
    row = conn.execute(text("SELECT value FROM number_sequences WHERE name = :n FOR UPDATE"), {"n": key}).first()
    if row is None:
        conn.execute(sequences.insert().values(name=key, value=1))
        value = 1
    else:
        value = row[0] + 1
        conn.execute(sequences.update().where(sequences.c.name == key).values(value=value))
    return f"{prefix}-{year}-{value:05d}"


def audit(conn: Connection, actor: str | None, action: str, object_type: str | None = None,
          object_id: str | int | None = None, detail: dict | None = None, ip: str | None = None) -> None:
    conn.execute(audit_log.insert().values(actor=actor, action=action, object_type=object_type,
                                           object_id=str(object_id) if object_id is not None else None,
                                           detail=detail or {}, ip=ip))


def tombstone(conn: Connection, object_type: str, object_id: str | int) -> None:
    conn.execute(tombstones.insert().values(object_type=object_type, object_id=str(object_id)))


def create_schema(engine: Engine | None = None) -> None:
    engine = engine or get_engine()
    metadata.create_all(engine)
    with engine.begin() as conn:
        current = conn.execute(schema_info.select().order_by(schema_info.c.id.desc())).first()
        if current is None:
            conn.execute(schema_info.insert().values(version=SCHEMA_VERSION))


def schema_version(conn: Connection) -> int | None:
    try:
        row = conn.execute(schema_info.select().order_by(schema_info.c.id.desc())).first()
    except Exception:
        return None
    return row.version if row else None


def db_now(conn: Connection) -> dt.datetime:
    from sqlalchemy import select
    return conn.execute(select(func.now())).scalar_one()
