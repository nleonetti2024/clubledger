"""ClubLedger — AI-assisted expense review for student clubs, with the treasurer in charge."""

from __future__ import annotations

import logging
from datetime import date

import click
from flask import Flask, g

from . import db
from .config import DEV_SECRET_KEY, DEV_TREASURER_PIN, PROJECT_ROOT, Config, load_dotenv
from .extraction import build_extractor, today
from .policy import load_policy

__version__ = "1.0.1"

log = logging.getLogger("clubledger")


def create_app(overrides: dict | None = None) -> Flask:
    load_dotenv()
    config = Config()
    for key, value in (overrides or {}).items():
        setattr(config, key, value)

    app = Flask(__name__)
    app.config.update(config.as_dict())
    app.config.update(
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )

    if not app.config["TESTING"]:
        if app.config["SECRET_KEY"] == DEV_SECRET_KEY:
            log.warning("Using the development SECRET_KEY. Set CLUBLEDGER_SECRET_KEY for real use.")
        if app.config["TREASURER_PIN"] == DEV_TREASURER_PIN:
            log.warning("Using the demo treasurer PIN (4010). Set CLUBLEDGER_TREASURER_PIN for real use.")

    policy = load_policy(app.config["POLICY_PATH"])
    primary, fallback = build_extractor(config, policy.category_keywords)
    app.extensions["clubledger"] = {"policy": policy, "extractor": primary, "fallback": fallback}

    def get_conn():
        if "db" not in g:
            g.db = db.connect(app.config["DATABASE"])
            db.init_schema(g.db)
        return g.db

    app.get_conn = get_conn  # type: ignore[attr-defined]

    @app.teardown_appcontext
    def _close(_exc):
        conn = g.pop("db", None)
        if conn is not None:
            conn.close()

    def as_of() -> date:
        fixed = app.config.get("AS_OF")
        return date.fromisoformat(fixed) if fixed else today()

    app.as_of = as_of  # type: ignore[attr-defined]

    from .web import bp

    app.register_blueprint(bp)
    _register_cli(app)
    return app


def _register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db_command():
        """Create the database tables."""
        conn = app.get_conn()
        db.init_schema(conn)
        click.echo(f"Database ready at {app.config['DATABASE']}")

    @app.cli.command("seed-demo")
    def seed_demo_command():
        """Submit the sample receipts in data/sample_receipts as demo members."""
        import json

        from .workflow import submit_expense

        ext = app.extensions["clubledger"]
        conn = app.get_conn()
        manifest = json.loads((PROJECT_ROOT / "data" / "sample_receipts" / "expected.json").read_text())
        for case in manifest["cases"]:
            text = (PROJECT_ROOT / "data" / "sample_receipts" / case["file"]).read_text()
            result = submit_expense(
                conn, member=case["member"], purpose=case["purpose"],
                claimed_amount=case["claimed_amount"], receipt_text=text,
                extractor=ext["extractor"], fallback=ext["fallback"], policy=ext["policy"],
                max_chars=app.config["MAX_RECEIPT_CHARS"], as_of=app.as_of(),
            )
            ids = ",".join(f["rule_id"] for f in [x.to_dict() for x in result.flags]) or "-"
            click.echo(f"#{result.expense_id:<3} {case['file']:<28} flags: {ids}")
