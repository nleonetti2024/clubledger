# Changelog

All notable changes are recorded here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses [Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-11

### Added
- Member submission of receipt text (paste or `.txt` upload) with purpose and claimed amount.
- Intake controls: card-number (Luhn-checked) and e-mail redaction, size limit, prompt-injection detection.
- AI extraction via the Anthropic Messages API with strict JSON schema validation.
- Offline rule-based reader, used when no API key is set and as the automatic fallback.
- Policy-compliance step with 11 rules (R1–R11), driven by `policy/club_policy.yaml`, each citing a policy section.
- Treasurer review queue sorted by severity, field corrections with re-check, approve / reject / needs-info.
- Override justification required to approve expenses with high-severity flags.
- Append-only audit log (enforced by database triggers) and CSV export of approved expenses.
- CSRF protection, security headers, role checks, member isolation, CSV formula-injection guard.
- 14 fictional sample receipts with expected results, `scripts/evaluate.py`, 94 automated tests, CI workflow.
