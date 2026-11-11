"""Web interface: member submission pages and the treasurer review queue."""

from __future__ import annotations

import csv
import hmac
import io
import secrets
from functools import wraps

from flask import (
    Blueprint, Response, abort, current_app, flash, redirect, render_template,
    request, session, url_for,
)

from . import __version__, db
from .policy import SEVERITY_ORDER, recommend
from .workflow import (
    APPROVED, DECISIONS, MIN_OVERRIDE_REASON, NEEDS_INFO, PENDING, REJECTED,
    WorkflowError, decide_expense, submit_expense,
)

bp = Blueprint("main", __name__)

DECISION_LABELS = {APPROVED: "Approved", REJECTED: "Rejected", NEEDS_INFO: "Needs info",
                   PENDING: "Pending review"}


def _ext():
    return current_app.extensions["clubledger"]


# --------------------------------------------------------------------------- display

@bp.app_template_filter("details_json")
def _details_json(value) -> str:
    """Readable JSON for audit details. Jinja autoescaping still escapes the HTML."""
    import json
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


# --------------------------------------------------------------------------- security

@bp.app_context_processor
def _inject():
    if "csrf" not in session:
        session["csrf"] = secrets.token_urlsafe(32)
    return {
        "csrf_token": session["csrf"],
        "user": session.get("user"),
        "role": session.get("role"),
        "club_name": _ext()["policy"].club_name,
        "status_labels": DECISION_LABELS,
        "version": __version__,
        "extractor_name": _ext()["extractor"].name,
    }


@bp.before_app_request
def _csrf_protect():
    if request.method == "POST":
        sent = request.form.get("csrf_token", "")
        expected = session.get("csrf", "")
        if not expected or not hmac.compare_digest(sent, expected):
            abort(400, description="Your form expired or was not sent from this site. Please try again.")


@bp.after_app_request
def _security_headers(resp: Response):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; style-src 'self'; img-src 'self' data:; form-action 'self'; frame-ancestors 'none'",
    )
    return resp


def login_required(role: str | None = None):
    def wrap(view):
        @wraps(view)
        def inner(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("main.login", next=request.path))
            if role and session.get("role") != role:
                abort(403, description="This page is only for the club treasurer.")
            return view(*args, **kwargs)
        return inner
    return wrap


# --------------------------------------------------------------------------- auth

@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:80]
        role = request.form.get("role", "member")
        if not name:
            flash("Please enter your name.", "error")
            return render_template("login.html"), 400
        if role == "treasurer":
            pin = request.form.get("pin", "")
            if not hmac.compare_digest(pin, current_app.config["TREASURER_PIN"]):
                conn = current_app.get_conn()
                db.add_audit(conn, None, name, "treasurer_login_failed", {})
                conn.commit()
                flash("That treasurer PIN is not correct.", "error")
                return render_template("login.html"), 401
        elif role != "member":
            abort(400)
        csrf = session.get("csrf")
        session.clear()
        session["csrf"] = csrf or secrets.token_urlsafe(32)
        session["user"], session["role"] = name, role
        return redirect(url_for("main.index"))
    return render_template("login.html")


@bp.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("main.login"))


@bp.get("/")
@login_required()
def index():
    if session["role"] == "treasurer":
        return redirect(url_for("main.review_queue"))
    return redirect(url_for("main.my_expenses"))


# --------------------------------------------------------------------------- member

@bp.route("/submit", methods=["GET", "POST"])
@login_required()
def submit():
    form = {"purpose": "", "claimed_amount": "", "receipt_text": ""}
    if request.method == "POST":
        form = {k: request.form.get(k, "") for k in form}
        upload = request.files.get("receipt_file")
        if upload and upload.filename:
            if not upload.filename.lower().endswith(".txt"):
                flash("Only .txt receipt files are supported in this prototype.", "error")
                return render_template("submit.html", form=form), 400
            form["receipt_text"] = upload.read().decode("utf-8", errors="replace")
        ext = _ext()
        try:
            result = submit_expense(
                current_app.get_conn(),
                member=session["user"],
                purpose=form["purpose"],
                claimed_amount=form["claimed_amount"],
                receipt_text=form["receipt_text"],
                extractor=ext["extractor"],
                fallback=ext["fallback"],
                policy=ext["policy"],
                max_chars=current_app.config["MAX_RECEIPT_CHARS"],
                as_of=current_app.as_of(),
            )
        except WorkflowError as exc:
            flash(str(exc), "error")
            return render_template("submit.html", form=form), 400
        flash("Submitted. The treasurer will review it — nothing is approved automatically.", "ok")
        return redirect(url_for("main.expense_detail", expense_id=result.expense_id))
    return render_template("submit.html", form=form)


@bp.get("/my")
@login_required()
def my_expenses():
    rows = db.list_expenses(current_app.get_conn(), member=session["user"])
    return render_template("my_expenses.html", expenses=rows)


# --------------------------------------------------------------------------- shared

@bp.get("/expenses/<int:expense_id>")
@login_required()
def expense_detail(expense_id: int):
    conn = current_app.get_conn()
    expense = db.get_expense(conn, expense_id)
    if expense is None:
        abort(404)
    is_treasurer = session["role"] == "treasurer"
    if not is_treasurer and expense["submitted_by"] != session["user"]:
        abort(404)  # do not reveal other members' expenses exist
    _, rec_text = recommend_from_dicts(expense["flags"])
    return render_template(
        "expense_detail.html",
        e=expense,
        x=expense["final_fields"] or expense["extraction"],
        audit=db.audit_for(conn, expense_id),
        is_treasurer=is_treasurer,
        rec_text=rec_text,
        categories=list(_ext()["policy"].categories),
        min_override=MIN_OVERRIDE_REASON,
        decisions=DECISIONS,
    )


def recommend_from_dicts(flags: list[dict]):
    class _F:  # minimal adapter so recommend() works on stored dicts
        def __init__(self, d):
            self.severity = d["severity"]
    return recommend([_F(f) for f in flags])


@bp.get("/policy")
@login_required()
def policy_page():
    return render_template("policy.html", p=_ext()["policy"])


# --------------------------------------------------------------------------- treasurer

@bp.get("/review")
@login_required("treasurer")
def review_queue():
    conn = current_app.get_conn()
    pending = db.list_expenses(conn, status=PENDING)
    pending.sort(key=lambda e: (
        min([SEVERITY_ORDER[f["severity"]] for f in e["flags"]] or [9]), e["id"]))
    decided = [e for e in db.list_expenses(conn) if e["status"] != PENDING][:20]
    return render_template("review_queue.html", pending=pending, decided=decided)


@bp.post("/expenses/<int:expense_id>/decide")
@login_required("treasurer")
def decide(expense_id: int):
    corrections = {k: request.form[k] for k in ("vendor", "date", "total", "category")
                   if k in request.form}
    try:
        decide_expense(
            current_app.get_conn(),
            expense_id=expense_id,
            treasurer=session["user"],
            decision=request.form.get("decision", ""),
            reason=request.form.get("reason", ""),
            corrections=corrections,
            policy=_ext()["policy"],
            as_of=current_app.as_of(),
        )
    except WorkflowError as exc:
        flash(str(exc), "error")
        return redirect(url_for("main.expense_detail", expense_id=expense_id))
    flash(f"Expense #{expense_id} recorded as {DECISION_LABELS[request.form['decision']].lower()}.", "ok")
    return redirect(url_for("main.review_queue"))


@bp.get("/audit")
@login_required("treasurer")
def audit_log():
    return render_template("audit.html", events=db.audit_for(current_app.get_conn())[:500])


def _csv_safe(value) -> str:
    """Stop spreadsheet formula injection when the CSV is opened in Excel/Sheets."""
    text = "" if value is None else str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@", "\t", "\r") else text


@bp.get("/export.csv")
@login_required("treasurer")
def export_csv():
    rows = db.list_expenses(current_app.get_conn(), status=APPROVED)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["id", "member", "purpose", "vendor", "date", "category", "amount",
                "approved_by", "approved_at", "note"])
    for e in reversed(rows):
        f = e["final_fields"] or e["extraction"]
        w.writerow([_csv_safe(v) for v in (
            e["id"], e["submitted_by"], e["purpose"], f.get("vendor"), f.get("date"),
            f.get("category"),
            f"{(f.get('total') if f.get('total') is not None else e['claimed_amount']):.2f}",
            e["decided_by"], e["decided_at"],
            e["decision_reason"])])
    db.add_audit(current_app.get_conn(), None, session["user"], "exported_csv", {"rows": len(rows)})
    current_app.get_conn().commit()
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=approved_expenses.csv"})


@bp.get("/healthz")
def health():
    return {"status": "ok", "version": __version__, "extractor": _ext()["extractor"].name}


@bp.app_errorhandler(400)
@bp.app_errorhandler(403)
@bp.app_errorhandler(404)
@bp.app_errorhandler(413)
def _error(err):
    code = getattr(err, "code", 500)
    msg = getattr(err, "description", "Something went wrong.")
    if code == 413:
        msg = "That file is too large (64 KB maximum)."
    return render_template("error.html", code=code, message=msg), code
