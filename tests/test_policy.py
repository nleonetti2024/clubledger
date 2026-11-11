
import pytest

from clubledger.extraction import Extraction, LineItem
from clubledger.policy import PolicyError, evaluate, load_policy, recommend
from conftest import AS_OF, POLICY_PATH


def x(**kw):
    base = dict(vendor="Shop", date="2026-11-10", total=50.0, category="food",
                line_items=[LineItem("thing", 50.0)], confidence=0.95)
    base.update(kw)
    return Extraction(**base)


def run(policy, extraction, claimed=None, text="", **kw):
    claimed = extraction.total if claimed is None else claimed
    return [f.rule_id for f in evaluate(extraction, policy, claimed_amount=claimed or 1.0,
                                        receipt_text=text, as_of=AS_OF, **kw)]


def test_clean_receipt_has_no_flags(policy):
    assert run(policy, x()) == []


def test_r1_over_category_limit(policy):
    assert "R1" in run(policy, x(total=150.01, line_items=[LineItem("a", 150.01)]))
    assert "R1" not in run(policy, x(total=150.00, line_items=[LineItem("a", 150.00)]))


def test_r2_prohibited_keyword_whole_word_only(policy):
    assert "R2" in run(policy, x(), text="Craft Beer 12pk")
    assert "R2" not in run(policy, x(), text="Wholesale chips")  # 'ale' inside 'Wholesale'


def test_r2_matches_line_item_descriptions(policy):
    assert "R2" in run(policy, x(line_items=[LineItem("Vodka", 50.0)]))


def test_r3_old_and_r8_future(policy):
    assert "R3" in run(policy, x(date="2026-09-01"))
    assert "R3" not in run(policy, x(date="2026-09-16"))  # exactly 60 days
    assert "R8" in run(policy, x(date="2026-12-01"))


def test_r4_duplicate(policy):
    assert "R4" in run(policy, x(), duplicate_of=[3])


def test_r5_claim_mismatch_respects_tolerance(policy):
    assert "R5" in run(policy, x(), claimed=60.0)
    assert "R5" not in run(policy, x(), claimed=50.40)


def test_r6_low_confidence(policy):
    assert "R6" in run(policy, x(confidence=0.5))


def test_r7_missing_fields(policy):
    assert "R7" in run(policy, x(vendor=None, date=None, total=None, line_items=[]), claimed=5)


def test_r9_math_mismatch(policy):
    assert "R9" in run(policy, x(line_items=[LineItem("a", 40.0)]))


def test_r10_and_r11(policy):
    ids = run(policy, x(), injection_markers=["ignore previous instructions"], used_fallback=True)
    assert "R10" in ids and "R11" in ids


def test_flags_sorted_high_first_and_cite_policy(policy):
    flags = evaluate(x(confidence=0.2, total=500.0, line_items=[LineItem("a", 500.0)]), policy,
                     claimed_amount=500.0, receipt_text="", as_of=AS_OF)
    assert flags[0].severity == "high"
    for f in flags:
        assert f.section.startswith("§") and f.policy_text


def test_recommendation_is_advisory_text_only(policy):
    assert recommend([])[0] == "looks_ok"
    flags = evaluate(x(total=999.0, line_items=[LineItem("a", 999.0)]), policy,
                     claimed_amount=999.0, receipt_text="", as_of=AS_OF)
    assert recommend(flags)[0] == "attention"


def test_policy_file_validation(tmp_path):
    bad = tmp_path / "p.yaml"
    bad.write_text("club_name: x\nreview: {}\ncategories: {}\nrules: {}\n")
    with pytest.raises(PolicyError):
        load_policy(bad)


def test_shipped_policy_loads():
    p = load_policy(POLICY_PATH)
    assert "other" in p.categories and p.limit_for("food") == 150.0
