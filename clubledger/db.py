"""SQLite storage for expenses and the audit trail.

Functions take an open sqlite3 connection so they can be used both from Flask
(per-request connection) and from scripts or tests.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS expenses (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    submitted_by     TEXT    NOT NULL,
    submitted_at     TEXT    NOT NULL,
    purpose          TEXT    NOT NULL,
    claimed_amount   REAL    NOT NULL,
    receipt_text     TEXT    NOT NULL,          -- already redacted
    redactions       TEXT    NOT NULL DEFAULT '[]',
    extraction       TEXT    NOT NULL,          -- JSON, as proposed by the extractor
    flags            TEXT    NOT NULL,          -- JSON list of policy flags
    recommendation   TEXT    NOT NULL,
    status           TEXT    NOT NULL DEFAULT 'pending_review',
    decided_by       TEXT,
    decided_at       TEXT,
    decision_reason  TEXT,
    final_fields     TEXT,                      -- JSON, after treasurer corrections
    CHECK (status IN ('pending_review','approved','rejected','needs_info'))
);
CREATE INDEX IF NOT EXISTS idx_expenses_status ON expenses(status);
CREATE INDEX IF NOT EXISTS idx_expenses_member ON expenses(submitted_by);

CREATE TABLE IF NOT EXISTS audit_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    expense_id  INTEGER REFERENCES expenses(id),
    at          TEXT    NOT NULL,
    actor       TEXT    NOT NULL,              -- a person's name or 'system:<step>'
    action      TEXT    NOT NULL,
    details     TEXT    NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_audit_expense ON audit_events(expense_id);

-- The audit trail is append-only: block edits and deletes at the database level.
CREATE TRIGGER IF NOT EXISTS audit_no_update BEFORE UPDATE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_no_delete BEFORE DELETE ON audit_events
BEGIN SELECT RAISE(ABORT, 'audit_events is append-only'); END;
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def connect(path: str) -> sqlite3.Connection:
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def add_audit(conn: sqlite3.Connection, expense_id: int | None, actor: str,
              action: str, details: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_events (expense_id, at, actor, action, details) VALUES (?, ?, ?, ?, ?)",
        (expense_id, now_iso(), actor, action, json.dumps(details or {}, sort_keys=True, ensure_ascii=False)),
    )


def row_to_expense(row: sqlite3.Row) -> dict:
    d = dict(row)
    for key in ("extraction", "flags", "redactions", "final_fields"):
        if d.get(key):
            d[key] = json.loads(d[key])
    return d


def get_expense(conn: sqlite3.Connection, expense_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM expenses WHERE id = ?", (expense_id,)).fetchone()
    return row_to_expense(row) if row else None


def list_expenses(conn: sqlite3.Connection, *, status: str | None = None,
                  member: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM expenses WHERE 1=1", []
    if status:
        sql += " AND status = ?"
        args.append(status)
    if member:
        sql += " AND submitted_by = ?"
        args.append(member)
    sql += " ORDER BY id DESC"
    return [row_to_expense(r) for r in conn.execute(sql, args).fetchall()]


def audit_for(conn: sqlite3.Connection, expense_id: int | None = None) -> list[dict]:
    if expense_id is None:
        rows = conn.execute("SELECT * FROM audit_events ORDER BY id DESC").fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM audit_events WHERE expense_id = ? ORDER BY id", (expense_id,)
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["details"] = json.loads(d["details"])
        out.append(d)
    return out
