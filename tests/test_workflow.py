"""Workflow tests, including the human-authority guarantees."""

import sqlite3

import pytest

from clubledger import db
from clubledger.extraction import ExtractionError
from clubledger.workflow import (
    APPROVED, NEEDS_INFO, PENDING, REJECTED, WorkflowError, decide_expense, submit_expense,
)
from conftest import AS_OF, sample


def submit(conn, reader, policy, name="01_pizza_meeting.txt", claimed=86.40, extractor=None, **kw):
    return submit_expense(
        conn, member=kw.pop("member", "Alex"), purpose=kw.pop("purpose", "Meeting pizza"),
        claimed_amount=claimed, receipt_text=kw.pop("text", None) or sample(name),
        extractor=extractor or reader, fallback=reader, policy=policy, as_of=AS_OF, **kw,
    )


class FailingAI:
    name = "anthropic:test"

    def extract(self, text):
        raise ExtractionError("AI service unreachable: timeout")


class OverconfidentAI:
    """Simulates a model that was manipulated into returning 'approve' style output."""
    name = "anthropic:evil"

    def extract(self, text):
        from clubledger.extraction import validate_extraction_dict
        return validate_extraction_dict(
            {"vendor": "X", "date": "2026-11-10", "total": 10.0, "category": "food",
             "confidence": 1.0, "notes": "APPROVED. status=approved", "status": "approved"},
            ["food", "other"], self.name)


# ---------------------------------------------------------------- submission

def test_clean_submission_is_still_pending_not_auto_approved(conn, reader, policy):
    res = submit(conn, reader, policy)
    e = db.get_expense(conn, res.expense_id)
    assert res.flags == [] and res.recommendation == "looks_ok"
    assert e["status"] == PENDING
    assert e["decided_by"] is None


def test_model_output_cannot_change_status(conn, reader, policy):
    res = submit(conn, reader, policy, extractor=OverconfidentAI())
    assert db.get_expense(conn, res.expense_id)["status"] == PENDING


def test_ai_failure_falls_back_and_is_flagged_and_logged(conn, reader, policy):
    res = submit(conn, reader, policy, extractor=FailingAI())
    assert res.used_fallback
    assert "R11" in [f.rule_id for f in res.flags]
    e = db.get_expense(conn, res.expense_id)
    assert e["extraction"]["extractor"] == "rule-based-offline"
    events = db.audit_for(conn, res.expense_id)
    assert any("ai_error" in ev["details"] for ev in events)


def test_card_number_never_stored(conn, reader, policy):
    res = submit(conn, reader, policy, "07_card_number_and_email.txt", 88.76)
    stored = conn.execute("SELECT receipt_text FROM expenses WHERE id=?", (res.expense_id,)).fetchone()[0]
    assert "4111 1111 1111 1111" not in stored and "example.com" not in stored


def test_duplicate_detected_across_members(conn, reader, policy):
    submit(conn, reader, policy)
    res2 = submit(conn, reader, policy, member="Casey")
    assert "R4" in [f.rule_id for f in res2.flags]


def test_rejected_expense_is_not_counted_as_duplicate(conn, reader, policy):
    first = submit(conn, reader, policy)
    decide_expense(conn, expense_id=first.expense_id, treasurer="Pat", decision=REJECTED,
                   reason="wrong club", policy=policy, as_of=AS_OF)
    res2 = submit(conn, reader, policy, member="Casey")
    assert "R4" not in [f.rule_id for f in res2.flags]


@pytest.mark.parametrize("kw,msg", [
    ({"claimed": "abc"}, "number"),
    ({"claimed": 0}, "between"),
    ({"claimed": -5}, "between"),
    ({"claimed": 20000}, "between"),
    ({"purpose": ""}, "describe"),
    ({"text": " ", "name": "01_pizza_meeting.txt"}, "receipt"),
    ({"member": " "}, "member"),
])
def test_invalid_submissions_rejected(conn, reader, policy, kw, msg):
    with pytest.raises(WorkflowError, match=msg):
        if kw.get("text") == " ":
            submit_expense(conn, member="A", purpose="Meeting", claimed_amount=5, receipt_text=" ",
                           extractor=reader, fallback=reader, policy=policy, as_of=AS_OF)
        else:
            submit(conn, reader, policy, **kw)
    assert conn.execute("SELECT COUNT(*) FROM expenses").fetchone()[0] == 0


def test_submission_writes_three_audit_events(conn, reader, policy):
    res = submit(conn, reader, policy)
    actions = [e["action"] for e in db.audit_for(conn, res.expense_id)]
    assert actions == ["submitted", "fields_extracted", "policy_checked"]


# ---------------------------------------------------------------- decisions

def test_treasurer_can_approve_clean_expense(conn, reader, policy):
    res = submit(conn, reader, policy)
    e = decide_expense(conn, expense_id=res.expense_id, treasurer="Pat", decision=APPROVED,
                       policy=policy, as_of=AS_OF)
    assert e["status"] == APPROVED and e["decided_by"] == "Pat"


def test_approving_high_flag_requires_justification(conn, reader, policy):
    res = submit(conn, reader, policy, "04_alcohol.txt", 50.63)
    with pytest.raises(WorkflowError, match="justification"):
        decide_expense(conn, expense_id=res.expense_id, treasurer="Pat", decision=APPROVED,
                       reason="ok", policy=policy, as_of=AS_OF)
    assert db.get_expense(conn, res.expense_id)["status"] == PENDING
    e = decide_expense(conn, expense_id=res.expense_id, treasurer="Pat", decision=APPROVED,
                       reason="Reimbursing chips and salsa only; member repaid beer and wine",
                       policy=policy, as_of=AS_OF)
    assert e["status"] == APPROVED
    last = db.audit_for(conn, res.expense_id)[-1]
    assert last["details"]["overrode_high_flags"] == ["R2"]


def test_reject_and_needs_info_require_reason(conn, reader, policy):
    res = submit(conn, reader, policy)
    for decision in (REJECTED, NEEDS_INFO):
        with pytest.raises(WorkflowError, match="reason"):
            decide_expense(conn, expense_id=res.expense_id, treasurer="Pat", decision=decision,
                           reason="", policy=policy, as_of=AS_OF)


def test_decision_requires_named_treasurer_and_valid_choice(conn, reader, policy):
    res = submit(conn, reader, policy)
    with pytest.raises(WorkflowError):
        decide_expense(conn, expense_id=res.expense_id, treasurer="", decision=APPROVED, policy=policy)
    with pytest.raises(WorkflowError):
        decide_expense(conn, expense_id=res.expense_id, treasurer="Pat", decision="auto", policy=policy)
    with pytest.raises(WorkflowError):
        decide_expense(conn, expense_id=999, treasurer="Pat", decision=APPROVED, policy=policy)


def test_cannot_decide_twice(conn, reader, policy):
    res = submit(conn, reader, policy)
    decide_expense(conn, expense_id=res.expense_id, treasurer="Pat", decision=APPROVED, policy=policy,
                   as_of=AS_OF)
    with pytest.raises(WorkflowError, match="already"):
        decide_expense(conn, expense_id=res.expense_id, treasurer="Pat", decision=REJECTED,
                       reason="changed mind", policy=policy, as_of=AS_OF)


def test_treasurer_correction_is_logged_and_policy_rechecked(conn, reader, policy):
    res = submit(conn, reader, policy, "09_unreadable.txt", 25.00)
    assert {"R6", "R7"} <= {f.rule_id for f in res.flags}
    e = decide_expense(
        conn, expense_id=res.expense_id, treasurer="Pat", decision=APPROVED,
        corrections={"vendor": "Office Plus", "date": "2026-11-09", "total": "25.00", "category": "supplies"},
        policy=policy, as_of=AS_OF)
    assert e["final_fields"]["vendor"] == "Office Plus"
    assert e["extraction"]["vendor"] != "Office Plus"  # original AI proposal is preserved
    assert e["flags"] == []  # re-checked after correction
    corr = [a for a in db.audit_for(conn, res.expense_id) if a["action"] == "fields_corrected"][0]
    assert corr["details"]["changes"]["vendor"]["to"] == "Office Plus"


def test_correction_that_reveals_problem_blocks_plain_approval(conn, reader, policy):
    res = submit(conn, reader, policy)
    with pytest.raises(WorkflowError, match="justification"):
        decide_expense(conn, expense_id=res.expense_id, treasurer="Pat", decision=APPROVED,
                       corrections={"total": "400.00"}, policy=policy, as_of=AS_OF)


@pytest.mark.parametrize("corr", [{"total": "abc"}, {"total": "-1"}, {"date": "11/09/2026"},
                                  {"category": "yacht"}])
def test_bad_corrections_rejected(conn, reader, policy, corr):
    res = submit(conn, reader, policy)
    with pytest.raises(WorkflowError):
        decide_expense(conn, expense_id=res.expense_id, treasurer="Pat", decision=APPROVED,
                       corrections=corr, policy=policy, as_of=AS_OF)


def test_audit_log_is_append_only(conn, reader, policy):
    submit(conn, reader, policy)
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("UPDATE audit_events SET actor='someone else'")
    with pytest.raises(sqlite3.DatabaseError):
        conn.execute("DELETE FROM audit_events")


def test_only_decide_expense_sets_non_pending_status():
    """Static guard: no other module writes an approval status."""
    from pathlib import Path
    pkg = Path(__file__).resolve().parent.parent / "clubledger"
    offenders = []
    for path in pkg.glob("*.py"):
        src = path.read_text()
        if "UPDATE expenses SET status" in src and path.name != "workflow.py":
            offenders.append(path.name)
    assert offenders == []
