"""Intake controls: clean, redact and screen receipt text before anything else.

This runs before the AI step and before anything is stored, so:
  * card numbers and e-mail addresses never reach the AI provider or the database;
  * oversize input is cut to a fixed limit;
  * text that looks like instructions to the review system (prompt injection)
    is detected and reported. It is *not* removed: the receipt is still treated
    purely as data, and a person must look at it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 13-19 digits, optionally separated by single spaces or dashes.
_CARD_RE = re.compile(r"(?<!\d)(?:\d[ -]?){12,18}\d(?!\d)")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

INJECTION_PATTERNS: tuple[str, ...] = (
    r"ignore\s+(all\s+|any\s+)?(the\s+)?(previous|prior|above|earlier)\s+(instructions|rules|prompts?)",
    r"disregard\s+(all\s+|the\s+)?(previous|prior|above|earlier)",
    r"you\s+are\s+now\b",
    r"system\s+prompt",
    r"\bapprove\s+(this|the)\s+(expense|receipt|request|reimbursement)",
    r"mark\s+(this|it)\s+as\s+approved",
    r"(set|change)\s+(the\s+)?status\s+to",
    r"</?\s*receipt\s*>",
    r"^\s*(system|assistant)\s*:",
)
_INJECTION_RES = [re.compile(p, re.IGNORECASE | re.MULTILINE) for p in INJECTION_PATTERNS]


@dataclass
class SanitizedText:
    text: str
    redactions: list[str] = field(default_factory=list)
    injection_markers: list[str] = field(default_factory=list)
    truncated: bool = False


def luhn_valid(digits: str) -> bool:
    """Standard Luhn checksum used by payment card numbers."""
    total = 0
    for i, ch in enumerate(reversed(digits)):
        n = int(ch)
        if i % 2 == 1:
            n *= 2
            if n > 9:
                n -= 9
        total += n
    return total % 10 == 0


def sanitize_receipt_text(raw: str, max_chars: int = 5000) -> SanitizedText:
    if raw is None:
        raw = ""
    text = raw.replace("\r\n", "\n").replace("\r", "\n")
    text = _CONTROL_RE.sub("", text)
    result = SanitizedText(text="")

    if len(text) > max_chars:
        text = text[:max_chars]
        result.truncated = True

    def _redact_card(match: re.Match) -> str:
        digits = re.sub(r"\D", "", match.group())
        if 13 <= len(digits) <= 19 and luhn_valid(digits):
            result.redactions.append("card_number")
            return f"[CARD ****{digits[-4:]}]"
        return match.group()

    text = _CARD_RE.sub(_redact_card, text)

    def _redact_email(_: re.Match) -> str:
        result.redactions.append("email")
        return "[EMAIL REDACTED]"

    text = _EMAIL_RE.sub(_redact_email, text)

    for pattern in _INJECTION_RES:
        m = pattern.search(text)
        if m:
            result.injection_markers.append(m.group().strip())

    result.text = text.strip()
    return result
