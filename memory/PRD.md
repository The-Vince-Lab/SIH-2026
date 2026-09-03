# SkillTrace AI — PRD

## Problem statement
Government skilling programs (PMKVY-style) track enrolment/attendance/certification but have
almost no reliable data on post-training outcomes (employment, retention, wage growth).
SkillTrace AI is a consent-based web platform that longitudinally tracks employment outcomes,
sends simulated WhatsApp/SMS follow-ups at 1/3/6/12 months, allows one-click employer
verification, and provides role-based analytics with an explainable AI layer and honest
data-confidence scoring (verified > self-reported > unreachable). SIH 2026 prototype.

## Architecture
- Frontend: React 19 + Tailwind + Recharts (JWT in localStorage, role-based routing).
- Backend: FastAPI + MongoDB (Motor). ML modules live in-process at `/backend/ml/`.
- Auth: JWT (HS256, Bearer), RBAC roles provider/district_admin/state_admin/super_admin,
  bcrypt hashing, email-based brute-force lockout.
- ML (scikit-learn + rapidfuzz): placement-risk (LogReg), identity matching (fuzzy),
  free-text classification (keyword + TF-IDF LogReg fallback). Artifacts persisted to disk.
- PII: phone numbers encrypted at rest (Fernet), only masked values returned.

## User personas
- Training Provider: enrolls trainees w/ consent, runs follow-ups, acts on at-risk cases.
- District/State Admin: compares providers/courses/districts, drills down.
- Super Admin: full access, user management.
- Trainee (subject, via simulator) and Employer (public verification, no login).

## Core requirements (static)
Unified profiles + identity matching · consent capture/revoke + audit · scheduled follow-ups ·
structured + free-text outcome capture · employer verification · wage/retention tracking ·
non-placement reasons · role-based analytics · explainable AI · confidence scoring.

## Implemented (with dates)
- 2026-06 Phase 0/1: collections, indexes, encrypted PII, seed (150 trainees, feature-correlated).
- 2026-06 Phase 2: JWT auth + RBAC, full REST API. Verified.
- 2026-06 Phase 3: three explainable ML modules + `/api/ml/*`. Metrics documented. Verified.
- 2026-06 Phase 4: ML wired into routes (duplicate block, free-text classify, risk endpoints). Verified 71/71.
- 2026-06 Phase 5: full React frontend (login, provider + admin dashboards, WhatsApp simulator,
  public employer verify, trainee journey timeline). Verified; enroll-RBAC, session-crash,
  simulator-state and gender-factor fairness bugs fixed.
- 2026-06 Phase 6: Consent Audit Trail viewer + logging, filter-aware CSV/PDF report export,
  wage-progression line chart on trainee journey. Verified full-stack (15/15 + 71 regression).

## Backlog (prioritized)
- P1: follow-up cycle "nothing due" info toast wording; shadcn Calendar for DOB; chart maxBarSize / axis label polish.
- P2: CSV/PDF report export; wage-progression-over-time chart; Hindi/Hinglish classifier expansion; /auth/me boot revalidation.
- P2: split server.py into routers; batch queries in at-risk/overview for scale.

## Next tasks
Awaiting user's Phase 6 instructions (consent audit trail / advanced governance per original spec).
