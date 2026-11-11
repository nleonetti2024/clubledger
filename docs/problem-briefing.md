# Problem briefing

## Scenario

A typical student club, such as a robotics club, has 30–80 members and a budget from student
government. Members often pay out of pocket for pizza, parts, printing or bus tickets, then ask
the treasurer to reimburse them. The treasurer is a student volunteer who has to check each
receipt against the club's spending rules and the student-government finance rules before
approving it.

## The problem

Checking receipts by hand is slow, inconsistent and easy to get wrong:

- Receipts arrive as photos, texts and e-mails, at irregular times, often in bursts after events.
- Rules are scattered across a constitution, a finance handbook and "what we did last year".
- Common mistakes include going over a category limit, reimbursing alcohol or gift cards (often
  banned for clubs funded by student fees), paying the same receipt twice, and paying the
  amount requested when it does not match the receipt.
- When something goes wrong, there is rarely a record of who approved what and why. That is a
  problem when the finance office audits the club.

## Stakeholders

| Stakeholder | Interest | What they need from a solution |
|---|---|---|
| **Treasurer** (primary user) | Accountable for the club's money | Less checking effort, consistent rule application, final say, a defensible record |
| **Club members** | Get reimbursed fairly and quickly | Simple submission, clear status and reasons |
| **Club president** | Club runs smoothly and keeps its funding | Visibility, fewer disputes |
| **Faculty advisor** | Oversight | Audit trail, policy compliance |
| **Student-government finance office** | Sets rules, audits clubs | Rules applied as written, records available |

## Goal

Help the treasurer review reimbursement requests faster and more consistently. AI does the
tedious reading. Deterministic rules do the checking. **The treasurer keeps every decision.**

## Why AI, and where

Reading receipts is a good fit for a language model because layouts, abbreviations and date
formats vary widely. Deciding whether club money may be spent is **not** delegated to AI. Those
rules must be predictable, explainable and auditable, so they are implemented as plain code
driven by a policy file.

## Success measures for the prototype

- Every planted policy problem in the sample set is flagged (flag recall = 100%).
- Few false alarms (flag precision ≥ 90%).
- Key fields are read correctly for at least 90% of sample receipts.
- 0 expenses change status without a named treasurer's decision.
- A new developer can clone, run and test the project in under 10 minutes without an API key.

## Scope

**In scope (prototype):** text receipts, one club, member submission, AI or offline extraction,
11 policy checks, treasurer review with corrections and override justification, audit log, CSV export.

**Out of scope:** photo or PDF OCR, real authentication or single sign-on, payments, multiple
clubs, mobile app, integration with university finance systems.

## Assumptions

- The club has written spending rules that can be expressed as limits, keywords and time windows.
- The treasurer is willing to review every request. The tool reduces effort; it does not remove the review.
- Sample data is fictional. Real use needs the club's and the university's permission before
  receipts are sent to an external AI service.
