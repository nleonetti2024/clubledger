# Traceability matrix

Problem → requirement → design element → code → verification → evidence.

Problem drivers (from [problem-briefing.md](problem-briefing.md)):
**P1** slow manual reading · **P2** inconsistent rule checks · **P3** costly mistakes (limits,
alcohol, duplicates, wrong amounts) · **P4** no record of who approved what · **P5** sensitive
data in receipts · **P6** the treasurer must stay accountable.

| Req | Driver | Design element | Code | Verified by | Evidence |
|---|---|---|---|---|---|
| FR-1 | P1 | Submission form, input validation | `web.submit`, `workflow._validate_submission` | `test_full_happy_path`, `test_invalid_submissions_rejected` (7 cases), `test_invalid_amount_shows_error_and_keeps_form`, `test_txt_upload_supported_and_other_types_refused` | Screenshots 01, 02 |
| FR-2 | P1 | Extraction agent + offline reader | `extraction.AnthropicExtractor`, `RuleBasedExtractor` | `test_reader_*`, `test_parse_date` (7 cases), `test_ai_extractor_parses_valid_json`, `test_ai_extractor_accepts_code_fenced_json` | Evaluation: field accuracy 98.2% |
| FR-3 | P2, P3 | Policy-compliance step, rule catalogue in YAML | `policy.evaluate`, `club_policy.yaml` | `test_policy.py` (R1–R11 incl. boundaries), `test_flags_sorted_high_first_and_cite_policy` | Evaluation: flag precision and recall 100%; screenshot 04 |
| FR-4 | P3 | Duplicate lookup | `workflow.find_duplicates` | `test_duplicate_detected_across_members`, `test_rejected_expense_is_not_counted_as_duplicate`, `test_r4_duplicate` | Sample 13 → R4 |
| FR-5 | P6 | Advisory recommendation | `policy.recommend` | `test_recommendation_is_advisory_text_only`, `test_clean_submission_is_still_pending_not_auto_approved` | Screenshot 04 ("Advisory: …") |
| FR-6 | P1 | Severity-sorted queue | `web.review_queue` | `test_full_happy_path` | Screenshot 03 |
| FR-7 | P4, P6 | Decision gate | `workflow.decide_expense` | `test_treasurer_can_approve_clean_expense`, `test_reject_and_needs_info_require_reason`, `test_cannot_decide_twice`, `test_decision_requires_named_treasurer_and_valid_choice` | Screenshot 07 |
| FR-8 | P1, P4 | Corrections with re-check | `workflow._apply_corrections` | `test_treasurer_correction_is_logged_and_policy_rechecked`, `test_correction_that_reveals_problem_blocks_plain_approval`, `test_bad_corrections_rejected` (4 cases) | Audit event `fields_corrected` |
| FR-9 | P4 | Member view + ownership check | `web.my_expenses`, `web.expense_detail` | `test_members_cannot_see_each_others_expenses`, `test_full_happy_path` | — |
| FR-10 | P4 | CSV export | `web.export_csv` | `test_full_happy_path`, `test_csv_export_neutralises_formulas` | — |
| FR-11 | P4 | Append-only audit log | `db.add_audit`, DB triggers | `test_submission_writes_three_audit_events`, `test_audit_log_is_append_only`, `test_wrong_treasurer_pin_refused_and_logged` | Screenshot 08 |
| FR-12 | P2 | Policy file | `policy.load_policy` | `test_policy_file_validation`, `test_shipped_policy_loads` | `/policy` page (screenshot 10) |
| NFR-1 | P6 | Structural gate, override justification | `workflow.py` | `test_model_output_cannot_change_status`, `test_only_decide_expense_sets_non_pending_status`, `test_approving_high_flag_requires_justification`, `test_flagged_expense_shows_policy_citation_and_needs_override` | Evaluation: 14/14 left pending; screenshot 06 |
| NFR-2 | P5 | Redaction before AI and storage | `sanitize.py` | `test_valid_card_number_is_redacted_keeping_last_four`, `test_number_failing_luhn_is_not_redacted`, `test_email_is_redacted`, `test_card_number_never_stored` | Screenshot 09 |
| NFR-3 | P3, P6 | Injection screen, delimited prompt, schema validation | `sanitize.py`, `extraction.py` | `test_injection_phrases_are_detected_but_text_kept_as_data`, `test_fake_receipt_tags_are_detected`, `test_ai_request_treats_receipt_as_delimited_data`, `test_validation_rejects_bad_output` (8 cases), `test_injection_receipt_shown_escaped_and_flagged` | Sample 08 → R10; screenshot 05 |
| NFR-4 | P5 | Web security controls | `web.py` | `test_post_without_csrf_token_is_refused`, `test_security_headers_present`, `test_member_cannot_open_treasurer_pages`, `test_pages_require_login`, `test_csv_export_neutralises_formulas` | — |
| NFR-5 | P1 | Fallback to offline reader | `workflow.submit_expense` | `test_ai_failure_falls_back_and_is_flagged_and_logged`, `test_ai_extractor_network_error_becomes_extraction_error`, `test_ai_extractor_rejects_non_json` | Audit `ai_error` detail |
| NFR-6 | P4 | Citations + audit | `policy._flag`, `db.py` | `test_flags_sorted_high_first_and_cite_policy`, `test_audit_log_is_append_only` | Screenshots 04, 07, 08 |
| NFR-7 | — | Offline default | `extraction.build_extractor` | `test_build_extractor_uses_offline_reader_without_key`, CI workflow | `pytest` passes with no network |
| NFR-8 | P1 | Lightweight stack, AI timeout | `config.AI_TIMEOUT_SECONDS` | Timing script (50 submissions) | Median 3.4 ms, p95 4.1 ms offline |
| NFR-9 | — | Lint, tests, CI | `pyproject.toml`, `.github/workflows/ci.yml` | `ruff check .`, `pytest` | 0 lint findings, 94/94 tests pass |
