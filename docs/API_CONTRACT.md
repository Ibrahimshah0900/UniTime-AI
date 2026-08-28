# UniTime-AI backend API contract

Contract version: `0.18.0`

The exact OpenAPI snapshot is committed as `docs/openapi.json`. JSON requests reject unknown fields where request models use `extra="forbid"`. Authenticated requests send `Authorization: Bearer <access_token>`.

## Error contract

Expected HTTP failures use:

```json
{
  "success": false,
  "error": "Human-readable message",
  "status_code": 400,
  "request_id": "request-id-or-null"
}
```

Validation failures use status 422 and add `details`, containing safe `location`, `message`, and `type` fields. Authentication failures are 401 with `WWW-Authenticate: Bearer`; authenticated but unauthorized roles receive 403. Ownership-protected resources return 404 rather than revealing another user's resource.

## Authorization matrix

- Public: `POST /auth/login`, `/`, `/health`, `/ready`. `POST /auth/register` is a local compatibility route controlled by `ALLOW_PUBLIC_STUDENT_REGISTRATION` and is forbidden in production.
- Any authenticated role: `/auth/me` and password/account setup routes. Users with a temporary credential must change it before ordinary role endpoints become available.
- Ready authenticated roles: `/dashboard`, `/notifications*`, `/notification-preferences`, and read-only `/academic-terms*` access.
- Verified, active, onboarded student only: `/student/enrollments*`, `/student/timetable`, `/student/clash-reports*`.
- Faculty only: `/faculty/assignments`, `/faculty/timetable`, `/faculty/free-slots`, and own term-scoped `/faculty/availability` management.
- Coordinator/admin: student provisioning, roster import, faculty provisioning, course offerings, faculty designation/workload and availability management, deterministic timetable generation preview/apply, institutional timetable CRUD/import, clash analytics and fixes, optimizer plans/actions/history, faculty assignment management, clash-report review, notification job processing, audit/change history, read-only data-quality diagnostics, and resolver analytics.
- Admin only: `/admin/users*`.
- Coordinator/admin: create, activate, and archive academic terms. Only one term may be active; archived terms are read-only.

## Endpoint groups

| Group | Methods and paths | Contract purpose |
|---|---|---|
| Authentication | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` | Development-only compatibility registration, email/registration-number JWT login, current user and first-login state |
| Academic terms | `GET/POST /academic-terms`, `GET /academic-terms/current`, `POST /academic-terms/{id}/activate`, `POST /academic-terms/{id}/archive` | Explicit planning/active/archived lifecycle and current-term context |
| Account | `PATCH /account/profile`, `POST /account/change-password`, `GET/PATCH /account/student-profile` | Own permitted profile fields, mandatory temporary-password replacement, and student onboarding |
| Admin users | `GET/POST /admin/users`, `PATCH /admin/users/{user_id}` | Search/create/update roles and activation |
| Student provisioning | `GET/POST /students`, `GET/PATCH /students/{user_id}`, `POST /students/{user_id}/temporary-password`, `POST /students/import` | Coordinator/admin institutional identity, verification, activation, one-time credential reset, and transactional CSV/XLSX roster import |
| Dashboard | `GET /dashboard` | Role-specific operational summary |
| Student enrollments | `GET/POST /student/enrollments`, `POST /student/enrollments/validate`, `DELETE /student/enrollments/{id}` | Stable course/section/semester identity with live add-conflict preview |
| Student timetable | `GET /student/timetable` | Personal classes derived from enrollments |
| Clash reports | `GET/POST /student/clash-reports`, `GET /student/clash-reports/{id}` | Submit and track owned reports |
| Clash review | `GET /clash-reports`, `GET /clash-reports/clusters`, `GET/PATCH /clash-reports/{id}`, `GET /clash-reports/{id}/resolution-candidates`, `POST /clash-reports/{id}/resolution-candidates/{candidate_id}/apply` | Queue, PII-free duplicate clustering, verified lifecycle, deterministic report-scoped planning, and transactional shared resolution |
| Faculty | `GET /faculty/assignments`, `GET /faculty/timetable` | Own stable mappings and schedule |
| Faculty directory | `GET/POST /faculty-directory` | Paginated active-faculty lookup and coordinator/admin faculty provisioning |
| Faculty management | `GET/POST /faculty-assignments`, `DELETE /faculty-assignments/{id}` | Coordinator/admin class mapping |
| Course offerings | `GET/POST /course-offerings`, `PATCH/DELETE /course-offerings/{id}` | Planning-term lecture/lab offering metadata with semester, duration, section, and room/location |
| Faculty scheduling metadata | faculty profile/workload and availability routes | Lecturer/AP designation, 4/2 distinct-subject workload enforcement, and term-scoped true availability |
| Timetable generation | `POST /timetable-generation/preview`, `POST /timetable-generation/apply` | Deterministic planning-term generation with stale-preview protection and hard institutional constraints |
| Notifications | `GET /notifications`, `PATCH /notifications/{id}/read`, `POST /notifications/read-all` | Paginated inbox and read state |
| Preferences/jobs | `GET/PUT /notification-preferences`, `POST /notification-jobs/process` | Reminder preferences and idempotent generator |
| Timetable | `GET/POST /timetable`, `GET/DELETE /timetable/{id}`, `PATCH /timetable/{id}/room`, `PATCH /timetable/{id}/time`, `POST /timetable/import` | Institutional timetable management |
| Clash analytics | `GET /clashes`, `/clashes/room-suggestions`, `/clashes/student-risk`, `/clashes/student-groups`, `/clashes/student-resolutions` | Structural and student-risk analysis |
| Clash actions | `POST /clashes/room/{id1}/{id2}/apply-best-fix`, `POST /clashes/student-groups/{id}/apply-best-fix` | Validated fixes |
| Optimizer | `GET /optimizer/global`, `POST /optimizer/global/apply-best`, `GET /optimizer/plan`, `POST /optimizer/plan/apply` | Global and multi-step planning/execution |
| History | `GET /changes`, undo/redo routes under `/changes` and `/student-schedule-changes`, `GET /audit-trail` | Change inspection and rollback |
| Executions | `GET /optimizer/executions`, `GET /optimizer/executions/{id}`, undo/redo routes | Grouped execution history and rollback |
| Data quality | `GET /data-quality` | Coordinator/admin read-only, term-scoped institutional diagnostics with stable issue codes, severity, safe entity identifiers, explanations, and suggested corrections |
| Resolver analytics | `GET /resolver-analytics` | Coordinator/admin, term-scoped operational metrics derived only from live conflict state and persisted resolution/report events; unavailable rates are explicitly marked unavailable |
| Operations | `GET /health`, `GET /ready` | Liveness and strict DB migration readiness |

## Key request contracts

- Login accepts exactly one of `identifier` or legacy `email`, plus `password`. `identifier` may be a canonical registration number or email. Faculty, coordinator, and admin email login remains supported.
- Student provision requires `registration_number`, `full_name`, `department`, `program`, `batch`, `current_semester`, and `section`; `email` is optional. A caller may provide a temporary password or receive a cryptographically generated value once in the creation response. Plaintext credentials are never persisted or logged.
- Student roster import accepts multipart CSV/XLSX. `dry_run=true` previews the all-row validation summary; any invalid/duplicate-in-file row prevents application. `update_existing=true` updates institutional academic fields by registration number without implicitly changing verification or activation state. Existing rows are duplicates by default.
- Provisioned users must change their temporary password, which invalidates the first token. A verified student must then complete `/account/student-profile` onboarding before enrollment, personal timetable, or clash-report operations.
- Enrollment create/validate: `course_code`, `section`, `semester` (non-empty strings). Course and section identities are stored uppercase; semester casing is normalized consistently. Case-only variants are duplicates. `POST /student/enrollments/validate` is read-only and reports the proposed mapping, exact current personal timetable overlaps, and timetable-only alternate sections. Creation repeats the validation against live state and returns it as `conflict_validation`; the current institutional policy allows the authentic enrollment mapping while surfacing the conflict immediately. Alternatives explicitly do not verify capacity, eligibility, or approval and are never applied automatically. Dropping an enrollment immediately removes its enrollment-backed edges from the personal conflict graph.
- Clash-report create: 2–10 unique positive `timetable_entry_ids`, optional `notes`, optional `evidence_reference`. The service independently rechecks active/verified/onboarded identity, active-term enrollment, personal-timetable ownership, current entry state, and real overlap. Exact repeat submissions return 409.
- Clash review: `status` plus terminal `resolution_note`; duplicate status also requires `duplicate_of_report_id`. Resolving requires `resolution_reason` (`timetable_changed`, `enrollment_corrected`, `course_dropped`, or `other_verified_correction`). The service verifies the stated reason against the reporting student's current personal timetable, current enrollment mapping, and current institutional timetable; an unresolved personal conflict returns 409. Allowed transitions are `submitted -> under_review|rejected|duplicate` and `under_review -> resolved|rejected|duplicate`.
- Clash-report clusters: `GET /clash-reports/clusters` accepts `open_only`, `offset`, `limit`, and optional `term_id`. Results group exact term/fingerprint matches, retain individual report IDs and ownership, expose counts and reported class snapshots without student PII, and include enrollment-backed affected-student counts plus current-overlap and coverage indicators.
- Resolution-candidate query: optional report-owned `target_entry_id`, `limit` (1–100), and `include_rejected_limit` (0–100). The report must be open, belong to the active term, still reference current timetable entries, and still represent an overlap. Candidate generation never mutates the timetable.
- Resolution apply: `target_entry_id`, non-blank `resolution_note`, and `confirm_conditional`. The report must first be `under_review`. `CONDITIONALLY_SAFE` requires explicit confirmation; `INSUFFICIENT_DATA` and `REJECTED` can never be applied. The 24-character candidate ID is regenerated under the timetable write lock from live timetable, enrollment-evidence, and policy state; stale IDs return 409 without writes.
- Course offering create/update: planning-term `course_code`, `course_name`, semester `1..8`, `section`, `class_type` (`lecture|lab`), `duration_minutes`, and optional room/location. A lecture offering produces the required two weekly lecture days; a lab offering produces the required single lab day during generation.
- Faculty assignment create: `faculty_user_id`, `course_code`, `section`, `semester`. Planning-term assignment requires a matching course offering, one authoritative faculty owner per offered subject, an active faculty account, and a designation-backed workload within the Lecturer=4 / Assistant Professor=2 distinct-subject cap. Lecture and lab components of the same course count once.
- Faculty availability windows are term-scoped weekday `day`, `start_time`, `end_time` declarations. For structured scheduling, absence of availability means unavailable; timetable gaps from `/faculty/free-slots` are not treated as personal availability.
- Timetable-generation preview is read-only and returns a 64-character `preview_id`, readiness errors, unscheduled reasons, already-satisfied sessions, and deterministic proposals. Apply accepts `term_id` plus that `preview_id`, recomputes live state under the timetable write lock, rejects stale/blocked previews, creates only missing generated sessions, and is idempotent when the planning timetable already satisfies all offerings.
- Timetable time change: `day`, `start_time`, and `end_time`. Day/time values are normalized and the request is rejected if the destination violates institutional semester/day rules, true structured faculty availability, same-semester exclusivity, faculty/room safety, or increases cohort risk.
- Notification preferences: nullable reminder minutes (`5|10|15|30`), daily-summary flag/time, schedule-change flag, clash-report-update flag.
- Data-quality diagnostics: `GET /data-quality` accepts optional `term_id`. It is read-only and restricted to coordinator/admin. Findings use stable issue codes and avoid echoing unnecessary student PII. In addition to identity/timetable/enrollment/report integrity, diagnostics cover structured scheduling readiness such as offerings without faculty allocation, ambiguous legacy allocations, designation workload over-cap anomalies, missing faculty designation/availability or required-day availability, room-less offerings, and generated-entry policy/offering metadata drift. Checks remain limited to facts supported by the current schema; room-capacity/equipment problems are not invented when reliable metadata does not exist.
- Resolver analytics: `GET /resolver-analytics` accepts optional `term_id`. Current confirmed/inferred conflicts and structural clashes are recomputed from live term data; historical application/undo/redo and resolution metrics come from persisted events. Rates without a trustworthy denominator return an explicit unavailable metric rather than an estimate.
- Timetable create uses the strict `TimetableEntryCreate` schema in OpenAPI. Unknown fields are rejected and all text limits match their database columns. Import accepts multipart CSV/XLSX with configured size/type validation.

## Stable response conventions

- Collection APIs added after Phase 4 expose explicit totals or lists as shown in OpenAPI.
- Timetable entries, enrollments, faculty assignments, clash reports, notifications, and scheduling history expose `term_id`. Current operational APIs default to the active term; archived rows remain readable but cannot be mutated.
- Student clash-report detail includes immutable server-attached registration number, name, email, department, program, batch, semester, section, term, conflict fingerprint, class-item snapshots, and ordered event history. Later edits to the live profile do not rewrite report evidence.
- `/clashes/student-risk` uses active verified `StudentEnrollment` rows to create confirmed weighted edges. `affected_student_count` is the real edge weight. Timetable-only fallback is labeled `timetable_inference` and can only be probable/possible; it is suppressed when complete enrollment coverage disproves the heuristic pair. The summary reports unmapped enrollment rows as data-quality issues.
- `/clash-reports/{id}/resolution-candidates` preserves actual class duration, evaluates current room/faculty/section/same-semester clashes, structured faculty availability, and enrollment-backed student conflicts, applies the published institutional policy, and hard-rejects unsafe moves before ranking. Accepted planning states are `SAFE`, `CONDITIONALLY_SAFE`, and `INSUFFICIENT_DATA`; missing required enrollment or structured scheduling metadata is never presented as safe. Candidate IDs include timetable, enrollment evidence, generic policy, and structured institutional scheduling state (offerings, faculty allocations, faculty account state, and availability), so later execution and redo reject stale selections.
- Each accepted candidate includes `ranker` identity/version and a versioned, PII-free `features` object. The feature contract always has `hard_constraints_passed=true`; rejected candidates are excluded before ranking. The configured default is the frozen synthetic-only CatBoost `research-v1` ranking artifact documented in `docs/RANKER_CONTRACT.md`. Deterministic hard constraints remain authoritative, `INSUFFICIENT_DATA` is excluded from the ML contract, and model/schema/artifact/runtime failures fall back to deterministic weighted ranking. The CatBoost score is a planning rank signal, not a prediction of real-world safety or success.
- Successful candidate execution moves exactly one timetable entry, rechecks the live result, resolves every open report in the same term/fingerprint cluster with `resolution_reason=timetable_changed`, records the actor/candidate/safety status and resolution note in `student_schedule_changes`, appends per-report events, and creates schedule/report notifications in one transaction. The response includes `resolved_report_ids` and `resolved_report_count`; any failure rolls everything back. Linked undo reopens each cluster report whose personal conflict was actually restored; redo revalidates the original candidate and re-resolves cluster reports whose conflict is gone. Both append actor-attributed per-report events and notify the reporting students.
- Student schedule-change history exposes nullable `report_id`, `actor_user_id`, `candidate_id`, `safety_status`, and `report_resolution_note`. Legacy optimizer group changes keep `group_id`; report resolutions use `group_id=null`.
- Notifications contain parsed `payload`, `read_at`, and `created_at`; clients must use `type` for presentation behavior.
- `/dashboard` returns `{role, generated_for_day, data}`; `data` is role-specific and clients must branch on `role`.
- Clash, optimizer, execution, and history read endpoints publish their nested response schemas in OpenAPI. Mutation responses retain forward-compatible operation details while preserving the stable success/error envelope.

## Token handling

Access tokens are JWT bearer tokens with a configured lifetime. Store them using the platform's safest available mechanism, clear them on logout or 401, never place them in URLs, and never expose privileged tokens to logs. Password changes and account deactivation increment the account token version and immediately invalidate previously issued access tokens. The backend does not issue refresh tokens in contract version 0.18.0; clients return to login after expiry.


## Synthetic/demo data tooling

Synthetic data generation is deliberately outside normal API startup and production workflows. `scripts/generate_synthetic_demo.py` requires an explicit SQLite target and `--confirm-synthetic`, refuses the normal development database and non-empty targets, and generates clearly labeled DEMO/SYNTHETIC identities. It is intended for isolated testing and resolver benchmarking only; generated data is never presented as university data. See `docs/SYNTHETIC_DATA.md`.
