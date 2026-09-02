# SkillTrace AI — Architecture Notes

Longitudinal skilling-outcomes & employment-impact tracking platform (SIH 2026 prototype).

## Stack (as built)
- **Frontend:** React.js + Tailwind CSS + Recharts (later phases)
- **Backend:** FastAPI (Python end-to-end) — API + ML in one service
- **Database:** MongoDB (motor async driver)
- **AI/ML:** scikit-learn + rapidfuzz, as internal modules in `/backend/ml/` (no separate microservice)
- **Auth:** JWT-based RBAC (later phase)

> Note: original spec suggested PostgreSQL + Node/Express. Adapted to the managed
> React + FastAPI + MongoDB stack (user-approved). All features preserved. ObjectId
> references between collections act as foreign keys; Pydantic models enforce shape.

## Project structure
```
/frontend            React app
/backend             FastAPI app
  server.py          API entrypoint
  models.py          Pydantic models (BaseDocument + PyObjectId pattern)
  db.py              Mongo connection + index creation
  security.py        bcrypt password hashing, Fernet phone encryption
  seed.py            synthetic data seeding (python seed.py)
  ml/                internal ML modules (placement risk, identity match, text classify)
/docs                architecture notes
```

## MongoDB collections
`trainees`, `training_providers`, `training_programs`, `enrollments`, `followups`,
`employment_records`, `non_placement_reasons`, `users`, `consent_logs`.

References stored as `ObjectId` (e.g. `enrollments.trainee_id -> trainees._id`).

### Indexes
`users.email` (unique), `trainees.phone_number`, `trainees.district`,
`enrollments.trainee_id`, `enrollments.program_id`, `followups.trainee_id`,
`followups.enrollment_id`, `employment_records.trainee_id`,
`non_placement_reasons.trainee_id`, `training_programs.provider_id`,
`consent_logs.trainee_id`.

## Privacy
- Trainee `phone_number` is **encrypted at rest** (Fernet, key from `PHONE_ENCRYPTION_KEY`).
- `phone_masked` stored for display (e.g. `XXXXXX8821`).
- Consent captured with scope + audit trail in `consent_logs`.

## Confidence scoring
Every follow-up data point tagged: `verified` > `self_reported` > `unreachable`
(missing data is surfaced, not hidden).

## Seed data distribution (150 trainees)
- ~60% employed / self-employed / apprentice
- ~15% unreachable
- ~25% not placed (with varied non-placement reasons)

## Seed accounts
| Role | Email | Password |
|------|-------|----------|
| super_admin | admin@skilltrace.gov.in | Admin@123 |
| provider | provider@skilltrace.gov.in | Provider@123 |
| district_admin | district@skilltrace.gov.in | District@123 |
| state_admin | state@skilltrace.gov.in | State@123 |

## Phase log
- **Phase 0/1 (done):** scaffolding, collections, indexes, encrypted PII, seed script.
- **Phase 2 (done):** JWT auth + RBAC, full REST API (trainees, consent, enrollments,
  follow-ups, employment + public verification, non-placement, analytics). Verified.
- **Phase 3 (done):** three explainable ML modules inside the FastAPI service —
  identity matching (rapidfuzz), free-text classification (keyword + TF-IDF LogReg),
  placement-risk prediction (LogReg). Routes under `/api/ml/*`. Seed made
  feature-correlated so the risk model has real signal. Metrics in
  `ml_model_performance.md`. Verified (56/57 backend tests).
