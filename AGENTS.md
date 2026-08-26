# UniTime-AI — Repository Instructions

## Project purpose
UniTime-AI is a full-stack university timetable and clash-resolution system. It supports students, faculty, coordinators, and admins with institution-controlled identity, academic terms, enrollment-backed personal timetables, verified clash reports, deterministic safe resolution candidates, transactional apply/undo/redo, notifications, learning-event preparation, and a React/Vite frontend.

## Working directory
Primary Windows repository path: `D:\UniTime-AI`.

Work in the existing repository. Extend the proven architecture; do not create a parallel rewrite.

## Current architectural baseline
The repository has progressed beyond the historical Phase-5 handoff. The authoritative state is the actual Git history, migrations, tests, and API contract.

Known checkpoint before the current continuation:
- branch: `phase-6-faculty-access`
- commit: `8b2c437 Collect pii guarded domain learning events`
- Alembic head: `738057d5ac81`
- API contract before the quality/analytics continuation: `0.15.0`
- known green baseline: 257 backend tests passed, 1 skipped; 21 frontend tests passed; lint, typecheck, and production build passed

The current working branch may contain later commits. Always inspect Git and Alembic rather than resetting to the checkpoint above.

Never rewrite, squash, or reset existing project history without explicit approval.

## Mandatory workflow
Reliability matters more than shaving off one command.

1. Inspect the current Git state and relevant code before editing.
2. Make small, architecture-compatible changes.
3. Prefer readable edits; no opaque Base64 blobs or giant blind shell one-liners.
4. Compile changed Python code.
5. Run targeted tests for the changed subsystem.
6. Stop on the first real failure and fix the root cause before stacking more changes.
7. Run the full regression suite before a checkpoint.
8. Run `alembic check` whenever models/schema are involved.
9. Run `git diff --check` before committing.
10. Create focused local commits only after the milestone is green.

Do not claim success for tests or deployment steps that were not actually run.

## Windows / shell
The user works on Windows CMD/VS Code terminals.

- Prefer Windows-compatible commands.
- Use the project interpreter: `.venv\Scripts\python.exe`.
- Avoid fragile quoting-heavy commands and Bash-only constructs in user-facing instructions.
- Do not ask the user to manually edit code when the coding agent can make the edit safely.

A machine-specific pytest temp-directory permission issue may exist under `%TEMP%`. When present, use the already verified project-local workaround `--basetemp=data\pytest-opencode` rather than changing application logic.

## Git and safety
Allowed: inspect Git, selectively stage project files, create focused local commits after green verification.

Never perform without explicit approval:
- `git push`
- `git reset --hard`
- `git clean`
- force-push/rebase/history rewrite
- destructive deletion of project/user data

Never commit secrets, `.env`, local databases, generated demo databases, `node_modules`, build output, or agent-operation files.

## Database / migrations
Alembic is the sole schema owner. Application startup must not use `create_all()` as schema management.

Local development defaults to SQLite; production is PostgreSQL-ready via `DATABASE_URL`.

Before a schema checkpoint:
- inspect current migration head
- generate one focused migration only when required
- inspect the migration manually
- run upgrade/check in an isolated or appropriate environment
- preserve existing data semantics

Do not reset the development database merely to make migration problems disappear.

## Authentication, identity, and RBAC
Roles:
- `student`
- `faculty`
- `coordinator`
- `admin`

Preserve:
- JWT auth with token-version invalidation
- Argon2 password hashing
- student login by registration number or email
- faculty/coordinator/admin email login
- institution-controlled student provisioning/import
- temporary-password and first-login workflow
- verified student profile/onboarding
- faculty provisioning and assignments
- ownership protection
- production public-registration restrictions

Do not reintroduce unrestricted public institutional registration.

## Academic terms
The authoritative lifecycle is:

`planning -> active -> archived`

Planning is a draft workspace, active is current operational truth, archived terms are historical/read-only. Current APIs default to the active term where appropriate.

Do not destructively replace this lifecycle. A deeper same-term publication/version model is optional future work only if it can be integrated safely.

## Enrollment-backed schedules and conflict graph
Student enrollments use stable course/section/semester identities rather than direct timetable-entry foreign keys.

Personal timetable matching supports exact sections, combined sections, common/shared entries, missing timetable semester metadata, and normalized identities.

Confirmed student conflicts must come from actual active verified enrollment mappings. Heuristic timetable-only risks must remain explicitly labeled inferred/probable and must never be presented as confirmed enrollment evidence.

## Verified clash reporting
Students submit reports only for classes in their current personal timetable and for real current overlaps. Reports preserve immutable server-attached identity, term, class, and conflict snapshots.

Students may access only their own reports. Coordinator/admin review is audited.

A report must not become `resolved` merely because a reviewer selected a status and wrote a note. Verified resolution reasons are:
- `timetable_changed`
- `enrollment_corrected`
- `course_dropped`
- `other_verified_correction`

The backend must verify the reported live conflict is actually gone; otherwise resolution returns a conflict response.

## Duplicate clustering
Reports for the same underlying term/conflict may be clustered while preserving each report and owner. Cluster-level responses must not expose student names, emails, registration numbers, or user IDs.

## Deterministic safe resolution candidates
The application already has report-scoped candidate generation and ranking.

Candidate states:
- `SAFE`
- `CONDITIONALLY_SAFE`
- `INSUFFICIENT_DATA`
- `REJECTED`

Hard constraints are authoritative. Reject violations before ranking. `INSUFFICIENT_DATA` and `REJECTED` are never applicable. Conditional candidates require explicit coordinator confirmation.

Candidate IDs include relevant live timetable/policy/enrollment evidence so stale candidates are rejected at execution.

## Transactional apply / undo / redo
Resolution application must:
- regenerate/revalidate under the timetable write lock
- reject stale/unsafe candidates
- update only the intended timetable entry
- recheck the live result
- resolve matching reports only when the real overlap disappeared
- record report events, timetable history, actor/candidate/safety metadata, notifications, and learning signals
- commit atomically

Failure rolls everything back.

Undo must reopen any related report whose real conflict returns. Redo must regenerate/revalidate the candidate before reapplying.

## Enrollment add/drop validation
`POST /student/enrollments/validate` previews actual timetable overlaps and timetable-only alternate sections. It must not claim capacity, eligibility, seat availability, or institutional approval unless those facts are modeled and verified. Never auto-switch a student between sections.

## Learning / AI boundary
No production ML model is currently trained, selected, hosted, deployed, or allowed to bypass hard safety rules.

Allowed engineering work:
- deterministic safety and ranking
- feature extraction
- PII-guarded event collection
- dataset export
- synthetic benchmarks
- ranker interfaces
- future-model safety tests

Not part of coding-agent work:
- training/selecting a production ML algorithm
- hosting/deploying a model
- using an LLM as the timetable resolver
- inventing performance metrics

If ML is added later, it may rank candidates that already passed deterministic safety; it cannot override constraints.

## Synthetic/demo data
Synthetic generation is an isolated development/testing tool, never application-startup behavior and never production data.

Synthetic records must be unmistakably labeled DEMO/SYNTHETIC, use reserved/test identities, avoid real PII, refuse the normal development/production database, refuse populated targets, and remain deterministic for a given seed/configuration.

Generated databases and benchmark artifacts must not be committed.

## Data quality and resolver analytics
Coordinator/admin diagnostics must be read-only and privacy-conscious. Report only facts supported by the actual schema. Do not fabricate capacity/equipment issues or unavailable analytics.

Metrics without trustworthy denominators must be marked unavailable rather than estimated.

## Frontend
The React/Vite frontend is already integrated. Preserve the approved role-adaptive design; do not rebuild it from scratch or start an unrelated redesign.

Coordinator workflows should expose report clusters, ranked candidates, impact/safety explanations, confirmation, apply results, history, undo/reopen, safe redo, quality diagnostics, and resolver analytics without dumping raw JSON as the normal UX.

Maintain loading/error/empty/disabled/stale/success states and existing accessibility patterns.

## Testing expectations
Backend checkpoint:
- compile changed Python files or `compileall`
- targeted tests
- full `pytest` regression
- `alembic check`
- `git diff --check`

Frontend checkpoint:
- `npm run lint`
- `npm run typecheck`
- `npm test -- --run` or repository-established equivalent
- `npm run build`

Run Playwright E2E for full-stack role/resolution workflows when the environment supports it. Never claim it passed unless it actually ran.

Important end-to-end resolver invariant:
student provisioning/onboarding -> authentic enrollments -> conflict warning -> verified report -> coordinator cluster/candidates -> safe apply -> timetable changes -> related reports resolve because clash is gone -> student history/notification -> undo -> conflict/report reopen -> safe redo -> verified resolution again.

## Deployment boundary
The repository is deployment-ready in architecture but must not be called production-deployed until PostgreSQL migrations, role smoke tests, production-style E2E, notification worker, real secrets, HTTPS/domain/CORS/hosts, backups, and live smoke tests are verified.

Mobile/Capacitor packaging, GitHub release, and production hosting are intentionally after the web resolver is logically complete and fully verified.

## Startup inspection
At the beginning of any significant work, inspect at minimum:
1. `git branch --show-current`
2. `git status --short`
3. `git log --oneline -10`
4. `.venv\Scripts\python.exe -m alembic current`
5. `.venv\Scripts\python.exe -m alembic check`
6. relevant API contract, models, routes/services, tests, and frontend files

The repository itself is authoritative. Do not follow historical pause-point text when Git, migrations, and current code show later completed work.
