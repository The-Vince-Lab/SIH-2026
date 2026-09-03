# SkillTrace AI — Privacy & Consent Design

Privacy is a first-class feature of SkillTrace AI, not an afterthought. This document
describes the consent model, data-minimization approach, and access-control layers.

## 1. Consent model (granular, revocable)
At enrolment the provider must capture **explicit, informed consent** before any tracking.
The consent screen states exactly what is collected and why, and the trainee/provider
selects the **scopes** to share:

| Scope | What it covers |
|-------|----------------|
| `employment_status` | Whether the trainee is employed / self-employed / searching |
| `wage_data` | Monthly income bracket over time |
| `contact_for_verification` | Permission to contact an employer to verify |

Consent is stored on the trainee record as `consent = { given, timestamp, scope[] }`.
It can be updated (scope toggled) or fully revoked at any time.

### Enforcement (not just a UI toggle)
- **Wage data**: if `wage_data` is NOT in scope, wage is **never stored** (`POST /employment`
  drops the wage bracket), **never plotted** (`/wage-progression` returns `wage_consent:false`
  and no points), and **excluded from analytics** (`compute_summary` aggregates wage only over
  trainees who consented). CSV export shows `(consent off)` instead of a value.
- A trainee with **no scopes** collects no outcome data at all.
- **All write paths** (`POST /employment`, `/non-placement-reason`, follow-up respond, and
  follow-up scheduling) enforce active consent centrally via `assert_consent`, so once consent
  is revoked no further data can be collected for that person. Previously collected wage
  brackets are retained (already anonymized at the individual level) to keep aggregate wage
  statistics valid.

## 2. Data minimization
- **PII encrypted at rest**: phone numbers are Fernet-encrypted; APIs only ever return a
  masked value (`XXXXXX1234`). Raw phone numbers are never sent to the client.
- **Right to be forgotten (real DB operation)**: `POST /trainees/:id/revoke-consent` performs
  irreversible anonymization — name → `Anonymized Trainee #NNNN`, phone → `REDACTED`,
  employer contacts nulled, free-text follow-up responses cleared, consent withdrawn, and an
  `anonymized` flag set. **Aggregate rows are preserved** (district, gender, outcome type),
  so cohort counts and placement rates stay correct while the individual can no longer be
  identified. This is a database mutation, verifiable in MongoDB.

## 3. Access-control layers (RBAC)
- **JWT + role gate** on every endpoint (`provider`, `district_admin`, `state_admin`,
  `super_admin`).
- **Aggregation-only for admins**: analytics endpoints (`/analytics/overview`,
  `/analytics/*/summary`, demographic, non-placement) return only counts / percentages /
  averages — never raw PII lists. Trainee-level list endpoints (`/trainees`,
  `/trainees-overview`) **refuse** state/super-admin calls that don't drill into a specific
  provider / course / district (HTTP 403).
- **Providers are sandboxed** to their own trainees (scope derived from their programs plus an
  ownership stamp on trainees they create). District admins are scoped to their district.
- **Employer verification** is a public, single-use, expiring token — the employer sees only
  the one fact they are confirming, with no account and no access to the platform.

## 4. Accountability — audit trail
Every consent-relevant event is appended to the `consent_logs` collection
(`trainee_id, action, timestamp, scope, performed_by`) with actions:
`granted`, `scope_updated`, `revoked` (with `anonymized`), and `accessed` (data-access event
logged when a trainee profile is opened). The trainee profile page renders this as a
chronological **Consent Audit Trail**, giving auditors a complete accountability record.

## 5. Honest data quality (related principle)
Instead of hiding missing data, every data point carries a **confidence tier**
(`verified` > `self_reported` > `unreachable`) that is surfaced throughout the UI and analytics —
so decision-makers always know how trustworthy a number is.
