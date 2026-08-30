# UniTime-AI Repository Maintenance Guide

## Source of truth

The current `main` branch, Git history, Alembic migrations, tests, and committed API contract are authoritative.

Do not rely on old handoff notes or historical branch checkpoints when current repository state says otherwise.

## Project

UniTime-AI is a full-stack university timetable and clash-resolution platform for students, faculty, coordinators, and administrators.

Current architecture:

- Python 3.13 / FastAPI backend
- SQLAlchemy 2 + Alembic
- SQLite for local/demo use and PostgreSQL support
- React 19 + TypeScript + Vite frontend
- Capacitor Android client
- deterministic timetable/clash safety engine
- CatBoost `research-v1` experimental learning-to-rank layer
- GitHub Actions qualification

The current backend API contract is `0.18.0`.

## Engineering workflow

For every meaningful change:

1. inspect the current branch, status, recent history, relevant code, tests, and contracts;
2. understand the existing implementation before editing;
3. prefer the smallest correct change;
4. reuse existing services, utilities, platform features, and dependencies;
5. add or update focused tests;
6. run targeted verification immediately;
7. run full qualification before a release checkpoint;
8. run `alembic check` for schema/model changes;
9. run `git diff --check`;
10. stage only the exact intended paths.

Prefer root-cause fixes over patches around symptoms.

Avoid speculative abstractions, parallel implementations, unnecessary dependencies, and unrelated refactors.

## Git safety

Do not:

- use `git clean`;
- broadly stage with `git add .` or `git add -A`;
- rewrite, squash, force-push, or hard-reset published history without explicit approval;
- commit `.env`, secrets, databases, generated demo databases, `node_modules`, build outputs, IDE-local state, or private institutional data.

Use a focused branch for new feature work and merge only after CI passes.

## Database

Alembic is the sole schema owner.

Application startup must not use `create_all()` as production schema management.

For schema changes:

- inspect the current Alembic head;
- create one focused migration when required;
- inspect the migration;
- test upgrade/check;
- preserve existing data semantics.

Do not reset a real database to hide migration problems.

## Authentication and authorization

Roles:

- `student`
- `faculty`
- `coordinator`
- `admin`

Preserve:

- JWT authentication and token-version invalidation;
- Argon2 password hashing;
- role and ownership authorization;
- institution-controlled student/staff provisioning;
- temporary-password / first-login behavior;
- verified student onboarding;
- production restriction of public registration.

Do not weaken authorization to make a feature easier to implement.

## Academic terms

Lifecycle:

`planning -> active -> archived`

Planning is a draft workspace, active is operational truth, and archived terms are historical/read-only.

## Timetable and enrollment evidence

Student personal schedules are enrollment-backed.

Confirmed student conflicts must come from active verified enrollment mappings. Heuristic/inferred risk must remain explicitly distinguished from confirmed evidence.

Timetable import supports CSV/XLSX and must validate data transactionally.

## Clash reporting and resolution

Students may report only real current overlaps from their own current personal timetable.

Resolution candidates use these states:

- `SAFE`
- `CONDITIONALLY_SAFE`
- `INSUFFICIENT_DATA`
- `REJECTED`

Hard constraints are authoritative.

`REJECTED` and `INSUFFICIENT_DATA` candidates are never applicable. Conditional candidates require explicit coordinator confirmation.

Applying a resolution must revalidate live state under the timetable write lock and must keep change/report/history/notification effects atomic.

Undo/redo must preserve the same safety and audit guarantees.

## AI boundary

The included CatBoost model is:

- model: `research-v1`
- status: `EXPERIMENTAL_SYNTHETIC`
- training/evaluation origin: synthetic labels only

Mandatory runtime order:

1. deterministic candidate generation;
2. deterministic hard safety checks;
3. exclude `REJECTED` and `INSUFFICIENT_DATA`;
4. CatBoost may rank only `SAFE` and `CONDITIONALLY_SAFE`;
5. model/artifact/schema/feature/prediction failure falls back to `DeterministicWeightedRanker`;
6. selected actions are revalidated under the write lock before mutation.

Never let ML override hard constraints or make a candidate applicable.

Do not present synthetic evaluation metrics as real-university production accuracy.

Keep the model feature contract PII-free.

## Synthetic data

Synthetic generation is for development, demonstrations, and evaluation only.

It must remain:

- clearly labeled synthetic;
- isolated from real data;
- deterministic for a fixed seed/config;
- unable to overwrite the normal development/production database;
- excluded from version control as generated database files.

## Frontend

Preserve the existing role-adaptive React/Vite interface and API-client architecture.

Maintain:

- loading/error/empty/success states;
- accessibility patterns;
- role-appropriate navigation;
- clear distinction between 401 and 403 behavior;
- no direct database access from the frontend.

## Android

The Android client is generated from the same React frontend through Capacitor.

Local physical-device HTTP testing may explicitly enable cleartext development behavior. A production-hosted backend should use HTTPS.

The backend URL is build-time configuration through `VITE_API_BASE_URL`.

## Verification

Backend:

```powershell
python -m pytest tests -q
python -m alembic check
git diff --check
```

Frontend:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
npm.cmd run test:e2e
```

Android changes must also satisfy the existing Android GitHub Actions job.

API changes must update tests/contracts and regenerate `docs/openapi.json` when required.

## Documentation

Keep these synchronized with behavior:

- `README.md`
- `frontend/README.md`
- `docs/API_CONTRACT.md`
- `docs/openapi.json`
- `docs/PROJECT_GUIDE.md`
- `docs/TEACHER_RUN_GUIDE.md`
- `docs/DEPLOYMENT.md`
- `docs/AI_EVALUATION.md`
- `docs/RANKER_CONTRACT.md`
- `CHANGELOG.md`

## Privacy

Never commit:

- real student/faculty records;
- real institutional timetable files unless explicitly approved for public release;
- passwords or tokens;
- database exports;
- private handoff prompts;
- local machine configuration.

Public demos should use the synthetic dataset.
