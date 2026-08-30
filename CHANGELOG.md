# Changelog

All notable project-level changes are summarized here.

## v0.1.1 - 2026-08-30

### Repository audit

- Corrected stale API-contract and Alembic-head documentation.
- Replaced historical machine-specific agent instructions with current repository guidance.
- Removed tracked Android Studio project-state files and expanded local-state ignores.
- Refreshed GitHub Actions to supported Node-24-generation action majors.
- Aligned project/frontend/Android patch-version metadata.
- Clarified validation-fixture intent.
- Requalified backend, PostgreSQL, frontend, and Android jobs before release.

## v0.1.0 - 2026-08-30

### Application

- Full FastAPI + React/TypeScript timetable application.
- Role-aware student, faculty, coordinator, and administrator workflows.
- Academic terms, student/enrollment management, faculty assignments and availability.
- Timetable import/editing and institutional scheduling workflows.
- Clash detection, student reporting, coordinator review, candidate resolution, apply/history/undo.
- Notifications, analytics, and data-quality diagnostics.

### AI / scheduling

- Deterministic hard-safety layer remains authoritative.
- Frozen CatBoost `research-v1` learning-to-rank model included.
- PII-free feature contract and artifact validation.
- Deterministic ranking fallback on ML failure.
- Synthetic evaluation evidence documented in `docs/AI_EVALUATION.md`.

### Android

- Capacitor Android project included under `frontend/android`.
- Android CI compilation/build qualification.
- Physical-device local-network workflow validated during development.
- README documents how to rebuild for a different laptop LAN address.

### Quality

- Backend Pytest qualification.
- PostgreSQL smoke/concurrency checks.
- Frontend lint, typecheck, tests, build, and Playwright E2E.
- Docker build checks.
- Android Gradle build checks.

### Documentation

- Complete local demo instructions.
- Real-timetable import workflow.
- Teacher/reviewer run guide.
- Complete project/architecture guide.
- API, ranker, synthetic-data, learning-event, deployment, and AI-evaluation documentation.
