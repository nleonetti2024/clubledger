from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from clubledger import create_app, db  # noqa: E402
from clubledger.extraction import RuleBasedExtractor  # noqa: E402
from clubledger.policy import load_policy  # noqa: E402

SAMPLES = ROOT / "data" / "sample_receipts"
POLICY_PATH = ROOT / "policy" / "club_policy.yaml"
AS_OF = date(2026, 11, 15)


def sample(name: str) -> str:
    return (SAMPLES / name).read_text()


@pytest.fixture
def policy():
    return load_policy(POLICY_PATH)


@pytest.fixture
def reader(policy):
    return RuleBasedExtractor(policy.category_keywords)


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.init_schema(c)
    yield c
    c.close()


@pytest.fixture
def app(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.sqlite3"),
        "SECRET_KEY": "test-secret",
        "TREASURER_PIN": "2468",
        "EXTRACTOR": "mock",
        "ANTHROPIC_API_KEY": "",
        "AS_OF": AS_OF.isoformat(),
    })
    return app


@pytest.fixture
def client(app):
    return app.test_client()
