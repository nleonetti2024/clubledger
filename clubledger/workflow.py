"""Review workflow: the orchestrator that runs each step and enforces human authority.

    member submits
        -> intake controls (sanitize.py)        redact, size-limit, injection screen
        -> extraction agent (extraction.py)     AI proposes fields; offline fallback
        -> policy-compliance step (policy.py)   deterministic checks, cited flags
        -> advisory recommendation              shown to the treasurer only
        -> PENDING REVIEW                       <-- the pipeline always stops here
    treasurer decides (decide_expense)          approve / reject / needs info
        -> optional corrections, re-checked     every change is logged
        -> audit trail + CSV export of approved expenses

Human authority is structural: `submit_expense` can only ever create an expense
in `pending_review`, and the only function that writes any other status is
`decide_expense`, which requires a named treasurer and records who decided why.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import date

from . import db
from .extraction import Extraction, ExtractionError, Extractor, today
from .policy import Policy, evaluate, recommend
from .sanitize import sanitize_receipt_text

PENDING = "pending_review"
APPROVED = "approved"
REJECTED = "rejected"
NEEDS_INFO = "needs_info"
DECISIONS = (APPROVED, REJECTED, NEEDS_INFO)

MIN_REASON = 5            # characters, for reject / needs-info
MIN_OVERRIDE_REASON = 15  # characters, to approve despite high-severity flags
MAX_CLAIM = 10_000.00


class WorkflowError(ValueError):
    """A request that the workflow refuses (shown to the user as a message)."""


@dataclass
class SubmitResult:
    expense_id: int
    flags: list
    recommendation: str
    used_fallback: bool


def _validate_submission(member: str, purpose: str, claimed_amount, receipt_text: str) -> float:
    if not member or not member.strip():
        raise WorkflowError("A member name is required.")
    if not purpose or len(purpose.strip()) < 3:
        raise WorkflowError("Please describe what the purchase was for.")
    if len(purpose) > 300:
        raise WorkflowError("The purpose must be 300 characters or fewer.")
    try:
        amount = round(float(claimed_amount), 2)
    except (TypeError, ValueError):
        raise WorkflowError("The claimed amount must be a number, like 42.50.") from None
    if not (0 < amount <= MAX_CLAIM):
        raise WorkflowError(f"The claimed amount must be between 0.01 and {MAX_CLAIM:,.2f}.")
    if not receipt_text or len(receipt_text.strip()) < 10:
        raise WorkflowError("Please paste or upload the receipt text.")
    return amount


def find_duplicates(conn: sqlite3.Connection, extraction: Extraction) -> list[int]:
    if not (extraction.vendor and extraction.date and extraction.total is not None):
        return []
    ids = []
    rows = conn.execute(
        "SELECT id, extraction FROM expenses WHERE status != 'rejected'"
    ).fetchall()
    for row in rows:
        other = json.loads(row["extraction"])
        if (
            (other.get("vendor") or "").strip().lower() == extraction.vendor.strip().lower()
            and other.get("date") == extraction.date
            and other.get("total") is not None
            and abs(float(other["total"]) - extraction.total) < 0.01
        ):
            ids.append(row["id"])
    return ids


def submit_expense(
    conn: sqlite3.Connection,
    *,
    member: str,
    purpose: str,
    claimed_amount,
    receipt_text: str,
    extractor: Extractor,
    fallback: Extractor,
    policy: Policy,
    max_chars: int = 5000,
    as_of: date | None = None,
) -> SubmitResult:
    amount = _validate_submission(member, purpose, claimed_amount, receipt_text)
    member = member.strip()[:80]
    as_of = as_of or today()

    clean = sanitize_receipt_text(receipt_text, max_chars=max_chars)

    used_fallback = False
    ai_error = None
    try:
        extraction = extractor.extract(clean.text)
    except ExtractionError as exc:
        if fallback is extractor:
            raise
        ai_error = str(exc)
        extraction = fallback.extract(clean.text)
        used_fallback = True

    duplicates = find_duplicates(conn, extraction)
    flags = evaluate(
        extraction,
        policy,
        claimed_amount=amount,
        receipt_text=clean.text,
        as_of=as_of,
        injection_markers=clean.injection_markers,
        duplicate_of=duplicates,
        used_fallback=used_fallback,
    )
    rec_code, _ = recommend(flags)

    cur = conn.execute(
        """INSERT INTO expenses (submitted_by, submitted_at, purpose, claimed_amount,
               receipt_text, redactions, extraction, flags, recommendation, status)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            member, db.now_iso(), purpose.strip(), amount, clean.text,
            json.dumps(clean.redactions), json.dumps(extraction.to_dict()),
            json.dumps([f.to_dict() for f in flags]), rec_code, PENDING,
        ),
    )
    expense_id = cur.lastrowid
    db.add_audit(conn, expense_id, member, "submitted",
                 {"claimed_amount": amount, "redactions": clean.redactions,
                  "truncated": clean.truncated})
    details = {"extractor": extraction.extractor, "confidence": extraction.confidence}
    if ai_error:
        details["ai_error"] = ai_error[:200]
    db.add_audit(conn, expense_id, "system:extraction", "fields_extracted", details)
    db.add_audit(conn, expense_id, "system:policy", "policy_checked",
                 {"flags": [f.rule_id for f in flags], "recommendation": rec_code,
                  "as_of": as_of.isoformat()})
    conn.commit()
    return SubmitResult(expense_id, flags, rec_code, used_fallback)


EDITABLE_FIELDS = ("vendor", "date", "total", "category")


def _apply_corrections(extraction: Extraction, corrections: dict, policy: Policy) -> tuple[Extraction, dict]:
    changes = {}
    for key in EDITABLE_FIELDS:
        if key not in corrections:
            continue
        raw = corrections[key]
        raw = raw.strip() if isinstance(raw, str) else raw
        if key == "total":
            if raw in ("", None):
                new = None
            else:
                try:
                    new = round(float(raw), 2)
                except (TypeError, ValueError):
                    raise WorkflowError("Corrected total must be a number.") from None
                if new < 0:
                    raise WorkflowError("Corrected total cannot be negative.")
        elif key == "date":
            if raw in ("", None):
                new = None
            else:
                try:
                    new = date.fromisoformat(raw).isoformat()
                except ValueError:
                    raise WorkflowError("Corrected date must be YYYY-MM-DD.") from None
        elif key == "category":
            if raw not in policy.categories:
                raise WorkflowError(f"Unknown category: {raw}")
            new = raw
        else:
            new = (raw or None) and str(raw)[:120]
        old = getattr(extraction, key)
        if new != old:
            changes[key] = {"from": old, "to": new}
            setattr(extraction, key, new)
    if changes:
        # A person has now verified these fields.
        extraction.confidence = 1.0
        extraction.notes = "fields corrected by treasurer"
    return extraction, changes


def decide_expense(
    conn: sqlite3.Connection,
    *,
    expense_id: int,
    treasurer: str,
    decision: str,
    reason: str = "",
    corrections: dict | None = None,
    policy: Policy,
    as_of: date | None = None,
) -> dict:
    if not treasurer or not treasurer.strip():
        raise WorkflowError("A named treasurer must make the decision.")
    if decision not in DECISIONS:
        raise WorkflowError("Decision must be approve, reject or needs info.")
    expense = db.get_expense(conn, expense_id)
    if expense is None:
        raise WorkflowError("Expense not found.")
    if expense["status"] != PENDING:
        raise WorkflowError("This expense has already been decided.")
    reason = (reason or "").strip()[:1000]
    as_of = as_of or today()

    extraction = Extraction.from_dict(expense["extraction"])
    flags = expense["flags"]
    changes = {}
    if corrections:
        extraction, changes = _apply_corrections(extraction, corrections, policy)
        if changes:
            injection = sanitize_receipt_text(expense["receipt_text"]).injection_markers
            dupes = [i for i in find_duplicates(conn, extraction) if i != expense_id]
            flags = [f.to_dict() for f in evaluate(
                extraction, policy,
                claimed_amount=expense["claimed_amount"],
                receipt_text=expense["receipt_text"],
                as_of=as_of,
                injection_markers=injection,
                duplicate_of=dupes,
            )]

    high = [f for f in flags if f["severity"] == "high"]
    if decision == APPROVED and high and len(reason) < MIN_OVERRIDE_REASON:
        raise WorkflowError(
            f"This expense has {len(high)} high-severity flag(s). To approve it anyway, "
            f"write a justification of at least {MIN_OVERRIDE_REASON} characters."
        )
    if decision in (REJECTED, NEEDS_INFO) and len(reason) < MIN_REASON:
        raise WorkflowError("Please give the member a short reason.")

    if changes:
        db.add_audit(conn, expense_id, treasurer.strip(), "fields_corrected",
                     {"changes": changes, "flags_after": [f["rule_id"] for f in flags]})

    conn.execute(
        """UPDATE expenses SET status = ?, decided_by = ?, decided_at = ?,
               decision_reason = ?, final_fields = ?, flags = ?
           WHERE id = ? AND status = ?""",
        (decision, treasurer.strip(), db.now_iso(), reason,
         json.dumps(extraction.to_dict()), json.dumps(flags), expense_id, PENDING),
    )
    db.add_audit(conn, expense_id, treasurer.strip(), f"decision:{decision}",
                 {"reason": reason, "overrode_high_flags": [f["rule_id"] for f in high]
                  if decision == APPROVED else []})
    conn.commit()
    return db.get_expense(conn, expense_id)
