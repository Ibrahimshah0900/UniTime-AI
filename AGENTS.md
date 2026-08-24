# UniTime-AI — Codex Repository Instructions

## Project purpose
UniTime-AI is a university timetable clash-resolution system. The backend is a FastAPI application with SQLAlchemy/Alembic, authentication/RBAC, timetable import and clash detection, optimizer execution/rollback history, student enrollments, and personal timetables. The target is a production/deployment-ready application with role-specific workflows for students, faculty, coordinators, and admins.

## Working directory
Primary local repo path on Windows:

`D:\UniTime-AI`

Use the repository in place. Do not create a parallel rewrite unless explicitly requested.

## Current branch and exact pause point
Current intended branch:

`phase-5-clash-reporting`

Last committed checkpoint before Phase 5:

`86905b6 Add student enrollments and personal timetable`

Phase 5 has already started and there is intentionally uncommitted work in `backend/models.py`:

- `StudentClashReport`
- `StudentClashReportItem`
- `StudentClashReportEvent`

`python -m py_compile backend\models.py` passed after these models were added.

No clash-report Alembic migration has been generated or applied yet. No Phase 5 clash-report service/API/tests exist yet.

Do NOT automatically discard or restore the current uncommitted Phase 5 model work.

The next expected action is:

`alembic check`

The expected result is schema drift showing the new clash-report tables/indexes because the models exist but the migration does not yet. After inspecting that output, generate the migration, inspect it, then apply it.

## Last known green baseline
Before Phase 5 began:

- Full test suite: **125 passed**
- Alembic head: `90feb9f09ea3`
- `alembic check`: no new upgrade operations detected
- `git diff --check`: clean

Current Phase 5 model-only change has compiled successfully but has not yet been fully regression-tested or committed.

## Important Git checkpoints
Major known checkpoints include:

- `b7f09ee` — Backend V1 Core - Functionally Tested
- `4502d3e` — Phase 2 Global Optimizer and Multi-Step Safety
- `314a454` — Add automated optimizer safety tests
- `4725b07` — Add grouped optimizer execution history and rollback
- Phase 3 production-hardening commits ending with `40aaefa Complete production readiness hardening`
- `f3f6b55` — Add authentication and user roles
- `3a744f5` — Enforce role based access control
- `9439594` — Add privileged account provisioning
- `86905b6` — Add student enrollments and personal timetable

Never rewrite or squash project history without explicit approval.

## Development workflow — mandatory
Reliability matters more than shaving off one command.

Use a controlled fast-track workflow:

1. Inspect the current file(s) and Git state before editing.
2. Batch only a few closely related changes.
3. Prefer readable edits/patches. Do not use opaque Base64 blobs or giant blind one-liners.
4. After each meaningful code batch, run `py_compile` on touched Python files.
5. Run targeted tests for the changed feature.
6. Stop immediately on the first failure and fix it before stacking more changes.
7. Run the full regression suite before a Git checkpoint.
8. Run `alembic check` whenever models/schema are involved.
9. Run `git diff --check` before committing.
10. Create a focused Git commit only after everything is green.

If a patch goes wrong, prefer restoring the affected Sprint files to the last green Git checkpoint rather than layering more uncertain edits.

Do not ask the user to manually edit files when Codex can edit them directly.

## Windows / shell constraints
The user works on Windows CMD/VS Code terminals.

- Prefer Windows-compatible commands.
- Avoid shell constructs that depend on Bash unless you are running them yourself in a compatible environment.
- Do not emit placeholder commands containing literal `...`.
- Avoid fragile quoting-heavy one-liners.
- If creating or patching multiline files, use normal file editing capabilities directly rather than encoded terminal tricks.

## Python / local environment
The repo uses a virtual environment at:

`.venv`

Typical startup:

`cd /d D:\UniTime-AI`

`.venv\Scripts\activate`

Run API locally with:

`python -m uvicorn backend.app:app --reload`

Development docs:

`http://127.0.0.1:8000/docs`

## Database / migrations
Local development DB:

`data/unitime_ai.db`

Alembic is the sole schema owner. Do not reintroduce runtime `create_all()` ownership into application startup.

Production is intended to use a hosted database, likely PostgreSQL, via `DATABASE_URL`.

Important commands:

- `alembic current`
- `alembic check`
- `alembic revision --autogenerate -m "..."`
- inspect generated migration before `alembic upgrade head`
- `alembic upgrade head`

Migration head before Phase 5: `90feb9f09ea3`.

## Existing backend capabilities
### Core timetable / clash engine
Existing capabilities include:

- timetable CRUD
- CSV/XLSX timetable import
- course parsing
- room/faculty clash detection
- room suggestions/fixes
- student conflict-risk analysis
- student conflict groups/resolutions
- timetable change history
- student schedule change history
- undo/redo
- audit trail

### Optimizer
Existing capabilities include:

- global optimizer
- multi-step optimization plan
- optimizer safety rules
- grouped optimizer execution history
- grouped optimizer undo/redo
- no structural clash increase
- risk-cost improvement requirements
- student conflict-group safety
- confirmed-risk safety

Existing optimizer routes include:

- `GET /optimizer/global`
- `POST /optimizer/global/apply-best`
- `GET /optimizer/plan`
- `POST /optimizer/plan/apply`
- `GET /optimizer/executions`
- `GET /optimizer/executions/{execution_id}`
- `POST /optimizer/executions/{execution_id}/undo`
- `POST /optimizer/executions/{execution_id}/redo`

### Production hardening
Already implemented:

- environment-configurable DB
- Alembic migration ownership
- strict `/ready` migration-head check
- `/health`
- CORS config
- trusted hosts
- centralized logging
- request IDs
- safe API exception handling
- standardized validation/errors
- security headers
- production docs behavior
- upload hardening
- runtime production configuration validation
- dotenv loading

### Authentication / roles
Roles:

- `student`
- `faculty`
- `coordinator`
- `admin`

Authentication includes:

- Argon2 password hashing
- JWT access tokens
- `POST /auth/register` — public student registration only
- `POST /auth/login`
- `GET /auth/me`

Privileged users are provisioned through a CLI, not public self-registration:

`python -m backend.create_user --email <email> --name "<name>" --role faculty|coordinator|admin`

The CLI prompts for the password interactively so the password is not stored in shell history.

### RBAC
All 14 sensitive timetable/optimizer mutation routes are guarded for coordinator/admin access.

Expected behavior:

- anonymous: `401`
- student: `403`
- faculty: `403` for institutional timetable mutation
- coordinator: allowed
- admin: allowed

Permanent RBAC tests exist.

### Student enrollments / personal timetable
Student enrollment identity is intentionally stable and does NOT point directly to timetable entry IDs:

- `user_id`
- `course_code`
- `section`
- `semester`

This avoids enrollment breakage when timetable imports rebuild entries.

Existing endpoints:

- `GET /student/enrollments`
- `POST /student/enrollments`
- `DELETE /student/enrollments/{enrollment_id}`
- `GET /student/timetable`

Student-only guards apply.

Personal timetable matching rules currently account for real imported timetable data:

- course code must match
- enrolled section `A` matches timetable section `A`
- enrolled section `A` also matches combined section `A,C`
- timetable section `None` is treated as shared/common and included
- timetable semester `None` does not block a match
- when timetable semester is present, it must match enrollment semester

Real imported timetable data contains sections such as `A`, `B`, `C`, `A,C`, `B,C`, and some `None` sections. Many current timetable entries have `semester=None`.

## Phase 5 — Student clash reporting requirements
This is the current active phase.

The report workflow should support:

1. Authenticated student submits a clash report from the app.
2. Report references the relevant classes/timetable entries and stores stable snapshots such as course code, section, day, and time where appropriate.
3. Student may include notes/reason and an evidence reference/attachment reference if supported.
4. Coordinator/admin gets a review queue.
5. Status lifecycle:
   - `submitted`
   - `under_review`
   - `resolved`
   - `rejected`
   - `duplicate`
6. Duplicate reports should be linkable/groupable.
7. Resolution note should be stored.
8. Full event/audit history should record actions and status changes.
9. Students should only see their own reports.
10. Coordinator/admin can review/update reports.
11. Faculty should not gain coordinator/admin timetable mutation powers unless explicitly decided later.
12. Notifications will later be emitted for status changes/resolutions.

The current uncommitted models were designed to support this:

- `StudentClashReport`
- `StudentClashReportItem`
- `StudentClashReportEvent`

Inspect them before changing their design.

## Remaining roadmap after clash reporting
After Phase 5, continue roughly in this order unless repo evidence suggests a better dependency order:

1. Complete student clash reporting and coordinator/admin review queue.
2. Faculty-to-class mapping and faculty-specific schedule/access where needed.
3. Notifications and reminder preferences:
   - before-class reminders, e.g. 5/10/15/30 minutes
   - optional daily summaries
   - schedule-change notifications
   - room/time change notifications
   - cancellation notifications
   - clash-report status/resolution notifications
4. Role-specific dashboard APIs for student/faculty/coordinator/admin.
5. Final backend API contract cleanup and OpenAPI review.
6. Frontend integration.
7. End-to-end tests for all roles.
8. Production deployment configuration and CI/CD.
9. Hosted PostgreSQL migration/deployment.
10. Production smoke tests and release readiness.

## Frontend workflow — important
Do not independently redesign the frontend UX as an uncoordinated rewrite.

The agreed workflow is:

1. Backend/API requirements are finalized enough for frontend work.
2. ChatGPT prepares one comprehensive Gemini frontend prompt covering:
   - project goals
   - backend capabilities
   - architecture
   - API contract
   - roles
   - required screens/components/flows
   - clash-report and notification workflows
   - required frontend files/structure
   - integration constraints
   - what Gemini must not change
3. User gives that prompt to Gemini.
4. Gemini returns frontend code/ZIP.
5. ChatGPT/Codex reviews, verifies, fixes, integrates, and tests it against FastAPI.

Do not invent a parallel frontend before this workflow unless the user explicitly changes the plan.

## Deployment target
The final system should be deployment-ready so the user's laptop does not need to remain running.

Expected production components:

- hosted FastAPI backend
- hosted PostgreSQL or equivalent production DB
- production secrets via environment variables
- HTTPS/domain configuration
- migrations executed safely during deployment
- frontend/mobile client configured for production API
- CI/CD or repeatable deployment commands
- production smoke tests
- clear README/deployment documentation

Do not hardcode production secrets into the repository.

## Testing expectations
Do not claim a feature is complete until relevant tests are added and green.

Known green baseline before Phase 5:

`125 passed`

Use:

`python -m pytest tests -q`

Before a feature checkpoint also run:

- `python -m py_compile <touched files>`
- targeted feature tests
- `python -m pytest tests -q`
- `alembic check` when relevant
- `git diff --check`
- `git status --short`

## Initial Codex startup procedure
When starting work in this repo, first inspect rather than assume.

Run/read at minimum:

1. `git branch --show-current`
2. `git status --short`
3. `git log --oneline -8`
4. inspect the current `StudentClashReport`, `StudentClashReportItem`, and `StudentClashReportEvent` models
5. `python -m py_compile backend\models.py`
6. `alembic current`
7. `alembic check`

Expected current branch: `phase-5-clash-reporting`.

Expected uncommitted change: `backend/models.py` containing the Phase 5 clash-report models.

Do not auto-clean the working tree if that is what you find.

## Decision rule
Inspect existing code and extend the current architecture. Avoid parallel implementations, duplicate models, duplicate services, or replacing proven components without a concrete reason.

Preserve the existing tested behavior while adding the remaining functionality needed for a complete, deploy-ready UniTime-AI application.
