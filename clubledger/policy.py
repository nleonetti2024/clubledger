"""Policy-compliance step: deterministic checks of an extraction against club rules.

This step is intentionally *not* AI. Rules that decide whether money can be
spent should be predictable, testable and explainable, so each check is plain
code driven by `policy/club_policy.yaml`. Every flag carries the rule id and the
policy section it comes from (source traceability).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path

import yaml

from .extraction import Extraction

SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Flag:
    rule_id: str
    severity: str
    title: str
    message: str
    section: str
    policy_text: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Policy:
    club_name: str
    currency: str
    categories: dict
    prohibited_items: list
    rules: dict
    low_confidence_threshold: float
    receipt_max_age_days: int
    amount_tolerance: float

    @property
    def category_keywords(self) -> dict[str, list[str]]:
        return {name: list(c.get("keywords", [])) for name, c in self.categories.items()}

    def limit_for(self, category: str) -> float | None:
        cat = self.categories.get(category)
        return None if cat is None else float(cat["limit_per_receipt"])


class PolicyError(ValueError):
    pass


def load_policy(path: str | Path) -> Policy:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    try:
        review = data["review"]
        categories = data["categories"]
        rules = data["rules"]
        if "other" not in categories:
            raise PolicyError("policy must define an 'other' category")
        for cat in categories.values():
            float(cat["limit_per_receipt"])
        for rid in [f"R{i}" for i in range(1, 12)]:
            if rid not in rules:
                raise PolicyError(f"policy is missing rule {rid}")
            if rules[rid]["severity"] not in SEVERITY_ORDER:
                raise PolicyError(f"rule {rid} has an unknown severity")
        return Policy(
            club_name=data.get("club_name", "Club"),
            currency=data.get("currency", "USD"),
            categories=categories,
            prohibited_items=data.get("prohibited_items", []),
            rules=rules,
            low_confidence_threshold=float(review["low_confidence_threshold"]),
            receipt_max_age_days=int(review["receipt_max_age_days"]),
            amount_tolerance=float(review["amount_tolerance"]),
        )
    except (KeyError, TypeError) as exc:
        raise PolicyError(f"policy file is missing a required field: {exc}") from exc


def _flag(policy: Policy, rule_id: str, message: str) -> Flag:
    rule = policy.rules[rule_id]
    return Flag(
        rule_id=rule_id,
        severity=rule["severity"],
        title=rule["title"],
        message=message,
        section=rule["section"],
        policy_text=rule["text"],
    )


def find_prohibited(policy: Policy, text: str) -> list[tuple[dict, list[str]]]:
    """Return (prohibited item, matched keywords) pairs found in the text."""
    lowered = text.lower()
    hits = []
    for item in policy.prohibited_items:
        found = [kw for kw in item.get("keywords", [])
                 if re.search(rf"\b{re.escape(kw.lower())}\b", lowered)]
        if found:
            hits.append((item, found))
    return hits


def evaluate(
    extraction: Extraction,
    policy: Policy,
    *,
    claimed_amount: float,
    receipt_text: str,
    as_of: date,
    injection_markers: list[str] | None = None,
    duplicate_of: list[int] | None = None,
    used_fallback: bool = False,
) -> list[Flag]:
    """Run every policy check. Returns flags sorted by severity (high first)."""
    flags: list[Flag] = []
    cur = policy.currency

    # R7 missing fields
    missing = [n for n, v in (("vendor", extraction.vendor), ("date", extraction.date),
                              ("total", extraction.total)) if v in (None, "")]
    if missing:
        flags.append(_flag(policy, "R7", f"Could not find: {', '.join(missing)}."))

    # R1 category limit
    limit = policy.limit_for(extraction.category)
    if extraction.total is not None and limit is not None and extraction.total > limit:
        flags.append(_flag(
            policy, "R1",
            f"{extraction.total:.2f} {cur} is over the {extraction.category} limit of {limit:.2f} {cur}.",
        ))

    # R2 prohibited items
    searchable = receipt_text + "\n" + "\n".join(li.description for li in extraction.line_items)
    for item, words in find_prohibited(policy, searchable):
        quoted = ", ".join(f"“{w}”" for w in words[:5])
        flags.append(_flag(policy, "R2", f"{item['label']} ({item['section']}): receipt mentions {quoted}."))

    # R3 / R8 dates
    if extraction.date:
        receipt_date = date.fromisoformat(extraction.date)
        age = (as_of - receipt_date).days
        if age > policy.receipt_max_age_days:
            flags.append(_flag(
                policy, "R3",
                f"Receipt is {age} days old; the limit is {policy.receipt_max_age_days} days.",
            ))
        if age < 0:
            flags.append(_flag(policy, "R8", f"Receipt date {extraction.date} is after {as_of.isoformat()}."))

    # R4 duplicates
    if duplicate_of:
        ids = ", ".join(f"#{i}" for i in duplicate_of)
        flags.append(_flag(policy, "R4", f"Same vendor, date and total as expense {ids}."))

    # R5 claimed vs receipt
    if extraction.total is not None and abs(claimed_amount - extraction.total) > policy.amount_tolerance:
        flags.append(_flag(
            policy, "R5",
            f"Member claimed {claimed_amount:.2f} {cur} but the receipt total is {extraction.total:.2f} {cur}.",
        ))

    # R6 confidence
    if extraction.confidence < policy.low_confidence_threshold:
        flags.append(_flag(
            policy, "R6",
            f"Confidence {extraction.confidence:.2f} is below {policy.low_confidence_threshold:.2f}."
            + (f" Reader notes: {extraction.notes}" if extraction.notes else ""),
        ))

    # R9 arithmetic
    if extraction.total is not None and extraction.line_items:
        items_sum = round(sum(li.amount for li in extraction.line_items), 2)
        if abs(items_sum - extraction.total) > 0.02:
            flags.append(_flag(
                policy, "R9", f"Line items add up to {items_sum:.2f} but the total is {extraction.total:.2f}.",
            ))

    # R10 prompt injection
    if injection_markers:
        shown = "; ".join(f"“{m[:60]}”" for m in injection_markers[:3])
        flags.append(_flag(policy, "R10", f"Found: {shown}. The text was treated as data only."))

    # R11 fallback used
    if used_fallback:
        flags.append(_flag(policy, "R11", "The AI service failed; the offline reader produced these fields."))

    flags.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.rule_id))
    return flags


def recommend(flags: list[Flag]) -> tuple[str, str]:
    """Advisory recommendation shown to the treasurer. It never changes status."""
    if any(f.severity == "high" for f in flags):
        return "attention", "High-severity issues found. Review carefully before deciding."
    if flags:
        return "check", "Minor issues found. Verify the flagged items."
    return "looks_ok", "No policy issues found. Confirm against the receipt and decide."
