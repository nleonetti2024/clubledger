# Requirements baseline

Status: **Implemented** = built and verified by tests or evaluation. **Partial** = built with
documented limits. **Deferred** = planned but outside the prototype.

## Functional requirements

| ID | Requirement | Priority | Status |
|---|---|---|---|
| FR-1 | A member can submit an expense with a purpose, a claimed amount and receipt text (pasted or `.txt` upload). Invalid input is refused with a clear message. | Must | Implemented |
| FR-2 | The system extracts vendor, date, total, category, line items and a confidence score from the receipt. | Must | Implemented |
| FR-3 | The system checks each expense against the club policy and raises flags. Each flag states the rule id, severity, a specific message and the policy section and text. | Must | Implemented |
| FR-4 | The system flags possible duplicate receipts (same vendor, date and total as an existing non-rejected expense). | Must | Implemented |
| FR-5 | The system shows the treasurer an advisory recommendation. It never changes an expense's status. | Should | Implemented |
| FR-6 | The treasurer sees a review queue of pending expenses sorted with the most severe flags first. | Must | Implemented |
| FR-7 | The treasurer can approve, reject or request more info. Reject and needs-info require a reason. An expense can be decided only once. | Must | Implemented |
| FR-8 | The treasurer can correct extracted fields before deciding. Corrections are logged (before and after) and the policy check re-runs. | Must | Implemented |
| FR-9 | A member can see the status and treasurer note for their own expenses, and only their own. | Must | Implemented |
| FR-10 | The treasurer can export approved expenses to CSV. | Should | Implemented |
| FR-11 | Every submission, automated step, correction, decision, failed treasurer login and export is recorded in an audit log. | Must | Implemented |
| FR-12 | Category limits, keywords, prohibited items, time window and rule text are configurable in a policy file without code changes. | Should | Implemented |
| FR-13 | Members can submit photos or PDFs of receipts. | Could | Deferred (OCR) |
| FR-14 | A member can reply to a needs-info request on the same expense. | Could | Deferred |

## Policy rules (implemented by FR-3, FR-4)

| Rule | Check | Severity |
|---|---|---|
| R1 | Total over the category's per-receipt limit | high |
| R2 | Prohibited item keyword (alcohol, tobacco, gift cards) | high |
| R3 | Receipt older than the allowed window (60 days) | medium |
| R4 | Possible duplicate | high |
| R5 | Claimed amount differs from receipt total by more than $0.50 | high |
| R6 | Extraction confidence below 0.70 | medium |
| R7 | Vendor, date or total missing | medium |
| R8 | Receipt date in the future | medium |
| R9 | Line items do not add up to the total | low |
| R10 | Receipt contains instructions aimed at the system (prompt injection) | high |
| R11 | AI service failed and the offline reader was used | low |

## Quality requirements (non-functional)

| ID | Attribute | Requirement | Status |
|---|---|---|---|
| NFR-1 | **Human authority** | No automated component can set an expense to approved, rejected or needs-info. Approving an expense with a high-severity flag requires a written justification (≥ 15 characters) from a named treasurer. | Implemented |
| NFR-2 | **Privacy** | Payment card numbers (Luhn-valid) and e-mail addresses are redacted before the text reaches the AI service or the database. | Implemented |
| NFR-3 | **Security: AI** | Receipt text is treated as untrusted data. Injection attempts are detected and flagged, the receipt is delimited in the prompt, and model output must pass schema and range validation. | Implemented |
| NFR-4 | **Security: web** | CSRF tokens on all POSTs, role checks on treasurer pages, output escaping, Content-Security-Policy and other headers, CSV formula-injection guard, upload size limit. | Implemented |
| NFR-5 | **Reliability** | If the AI call fails or returns invalid output, the submission still succeeds using the offline reader and is flagged R11. | Implemented |
| NFR-6 | **Traceability** | Every flag cites a policy section. Every decision records who, when and why. The audit log is append-only. | Implemented |
| NFR-7 | **Reproducibility** | The app, tests and evaluation run without network access or an API key. Tests are deterministic. | Implemented |
| NFR-8 | **Performance** | Offline submission completes in under 1 second. The AI call times out after 20 seconds (configurable). | Implemented (median 3.4 ms offline) |
| NFR-9 | **Maintainability** | Lint-clean, automated tests and CI. Policy changes need no code changes. | Implemented |
| NFR-10 | **Usability** | Error messages say what to fix. The queue shows the riskiest items first. Flags explain themselves in plain language. | Implemented |
| NFR-11 | **Authentication** | Individual accounts with strong authentication. | Partial (shared treasurer PIN; SSO deferred) |

## Changes from the original plan

| Change | Reason | Effect |
|---|---|---|
| Added R10 (injection) and R11 (fallback) | Building the AI step showed that receipt text could carry instructions, and that the API can fail. Both need to be visible to the treasurer. | Two new rules, NFR-3 and NFR-5 strengthened |
| Added the override justification (NFR-1) | Without it, the treasurer could approve a flagged expense with one click, making the flags easy to ignore. | Decisions on risky items are now documented |
| Policy check is deterministic code, not AI | Rules about money must be predictable and testable. Letting a model decide would weaken traceability. | AI is limited to extraction |
| Text-only receipts (OCR deferred) | Keeps the prototype bounded and testable without paid services | FR-13 deferred |
| Added the offline reader | Lets graders and CI run everything free. Also serves as the fallback. | NFR-5 and NFR-7 met |
