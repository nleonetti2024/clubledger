# Contributing to ClubLedger

Thanks for helping. This project is small on purpose, so changes should keep it easy to understand and test.

## Ground rules

1. **The treasurer stays in charge.** No change may let any automated step (AI, rules or anything else) set an expense to approved, rejected or needs-info. `tests/test_workflow.py::test_only_decide_expense_sets_non_pending_status` enforces this.
2. **AI output is untrusted.** Anything a model returns must go through `validate_extraction_dict` before it is used.
3. **Policy lives in `policy/club_policy.yaml`.** Do not hard-code limits or keywords in Python.
4. **No real data.** Never commit real receipts, names, card numbers, API keys or database files.

## Development setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
pytest && ruff check .
```

## Making a change

1. Open an issue describing the problem or idea (use the templates).
2. Create a branch: `git checkout -b feature/short-description` or `fix/short-description`.
3. Write or update tests first when you can. Every new rule needs a test for when it fires and when it doesn't.
4. Run `pytest`, `ruff check .` and `python scripts/evaluate.py`. All must pass.
5. If behavior changes, update the README, `docs/requirements.md`, `docs/traceability.md` and `CHANGELOG.md`.
6. Open a pull request and fill in the template.

## Commit messages

Use short, imperative messages that explain *why*:

```
Add R8 future-date check

Receipts dated after submission were silently accepted. Flag them so the
treasurer can confirm the date.
```

Prefix suggestions: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`, `chore:`.

## Adding a policy rule

1. Add the rule (`R12`, …) with title, severity, section and text to `policy/club_policy.yaml`.
2. Add the check in `policy.evaluate()` using `_flag(policy, "R12", message)`.
3. Add tests in `tests/test_policy.py` and, if useful, a sample receipt plus an entry in `data/sample_receipts/expected.json`.
4. Update the rule list in the README and `docs/requirements.md`.

## Using AI assistants

You may use AI tools. Review everything they produce, run the tests, and note significant AI-generated changes and any rejected suggestions in `docs/ai-assistance-log.md`.
