# Validation plan and results

## Approach

The prototype was validated at three levels:

1. **Automated unit and integration tests** (`pytest`, 94 tests): each component on its own and the full web workflow.
2. **End-to-end evaluation** (`scripts/evaluate.py`): 14 fictional receipts covering normal, exception and attack cases, scored against expected results in `data/sample_receipts/expected.json`.
3. **Manual walkthrough** in a real browser (headless Chrome), with screenshots in `docs/images/`.

All results below come from the offline reader (`rule-based-offline`) on 2026-11-11, using
reference date 2026-11-15, Python 3.13 and Flask 3.1.

## 1. Automated tests

```
$ pytest -q
94 passed in 0.9s
$ ruff check .
All checks passed!
```

| Area | Tests | Normal | Exception / failure | Security |
|---|---|---|---|---|
| Intake controls | 9 | redaction, clean text | none input, truncation, control chars | Luhn false-positive check, injection detection |
| Extraction | 30 | normal receipt, date formats, AI JSON | unreadable receipt, non-JSON, schema violations (8), network error | prompt delimiting, fake closing tag |
| Policy | 15 | clean receipt | every rule R1–R11 incl. boundaries (exactly 150.00, exactly 60 days, $0.40 tolerance) | — |
| Workflow | 27 | approve clean, corrections | invalid submissions (7), AI fallback, double decision, bad corrections (4) | manipulated model output, append-only audit, static status-write guard |
| Web | 13 | full member → treasurer → CSV path | bad amount, wrong file type | CSRF, roles, PIN, headers, XSS escaping, member isolation, CSV formulas |

## 2. End-to-end evaluation

| Sample | Purpose of case | Expected | Observed | Result |
|---|---|---|---|---|
| 01 pizza | normal | no flags | no flags | Pass |
| 02 hardware | normal, many items | no flags | no flags | Pass |
| 03 catering | over food limit | R1 | R1 | Pass |
| 04 market | alcohol | R2 | R2 ("beer", "wine") | Pass |
| 05 copy center | 137 days old | R3 | R3 | Pass |
| 06 copy center | normal | no flags | no flags | Pass |
| 07 electronics | card number + e-mail | no flags, redacted | no flags, redacted card and e-mail | Pass |
| 08 rentals | prompt injection | R10 | R10, still pending | Pass |
| 09 faded | unreadable | R6, R7 | R6, R7 (vendor misread) | Flags pass, 1 field wrong |
| 10 bagels | items ≠ total | R9 | R9 | Pass |
| 11 bus | travel, "Oct 25, 2026" date | no flags | no flags | Pass |
| 12 campus store | gift card | R2 | R2 | Pass |
| 13 pizza again | duplicate of 01 | R4 | R4 | Pass |
| 14 office | claimed $32.45 vs receipt $23.45 | R5 | R5 | Pass |

**Summary:** field accuracy 55/56 = **98.2%** · flag precision **100%** · flag recall **100%** ·
**14/14** expenses left in `pending_review` for a human.

## 3. Quality attributes

| Attribute | How measured | Result |
|---|---|---|
| Human authority | Tests + evaluation: does any path set status without a treasurer? | No. 0 automated status changes. A manipulated model output stays pending. Override without justification is blocked (screenshot 06). |
| Privacy | Stored receipt text inspected after submitting sample 07 | Card number stored as `[CARD ****1111]`, e-mail as `[EMAIL REDACTED]` |
| Robustness to injection | Sample 08 + `<script>` payload | Flagged R10, text displayed escaped, status pending |
| Reliability | AI forced to fail (`FailingAI` test double) | Submission succeeds with the offline reader, R11 flag, error in audit log |
| Performance | 50 offline submissions through the web client | Median 3.4 ms, p95 4.1 ms, max 16 ms |
| Reproducibility | Clean run without network or key | All tests and evaluation pass |
| Maintainability | `ruff check .` | 0 findings |

## 4. Observed behavior and limitations found during validation

- **Messy text can produce a wrong vendor.** On sample 09 the offline reader took the junk line
  "it3ms ..... see back" as the vendor. Because the total and date were also missing,
  confidence fell to 0.20 and R6 and R7 were raised, so the treasurer is warned and can correct
  it. This was kept as-is rather than tuning the reader to the sample, which would have hidden a
  real weakness.
- **Keyword rules can miss synonyms** (e.g. "Bud Light" without the word "beer"). An AI-based
  "possible prohibited item" hint is a candidate improvement, but it would stay advisory.
- **The live AI path is verified with mocked HTTP only.** The network in the build environment
  could not reach the API. To record live evidence, run with a key:
  `CLUBLEDGER_EXTRACTOR=anthropic python scripts/evaluate.py --markdown docs/evaluation-results-ai.md`.
- **Duplicate detection is exact** on vendor, date and total. A re-typed receipt with a slightly
  different vendor spelling is not caught.

## How to reproduce

```bash
pip install -r requirements-dev.txt
pytest -v
python scripts/evaluate.py --markdown docs/evaluation-results.md
```
