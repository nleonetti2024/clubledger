# Security policy

## Supported versions

| Version | Supported |
|---|---|
| 1.0.x | Yes |

## Reporting a vulnerability

Please **do not open a public issue** for security problems. Use GitHub's
**"Report a vulnerability"** button (Security tab → Advisories) so the report stays private.
Include steps to reproduce, the affected version and the impact. You should get a reply within
seven days.

## Scope notes

ClubLedger is a course prototype. Known gaps are listed in the README under
*Known limitations*: there are no real user accounts, the treasurer role uses one shared PIN,
and the app runs on Flask's development server. Do not deploy it with real financial data
without fixing those first.

## Secrets

- Keep API keys and the session secret in `.env` (git-ignored) or in your host's secret store.
- If a key is ever committed, **revoke it immediately**. Deleting the commit is not enough.
