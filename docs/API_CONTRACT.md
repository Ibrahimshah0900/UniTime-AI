# UniTime-AI backend API contract

Contract version: `0.12.0`

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
- Faculty only: `/faculty/assignments`, `/faculty/timetable`.
- Coordinator/admin: student provisioning, roster import, faculty provisioning, institutional timetable CRUD/import, clash analytics and fixes, optimizer plans/actions/history, faculty assignment management, clash-report review, notification job processing, audit/change history.
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
| Student enrollments | `GET/POST /student/enrollments`, `DELETE /student/enrollments/{id}` | Stable course/section/semester enrollment identity |
| Student timetable | `GET /student/timetable` | Personal classes derived from enrollments |
| Clash reports | `GET/POST /student/clash-reports`, `GET /student/clash-reports/{id}` | Submit and track owned reports |
| Clash review | `GET /clash-reports`, `GET/PATCH /clash-reports/{id}`, `GET /clash-reports/{id}/resolution-candidates`, `POST /clash-reports/{id}/resolution-candidates/{candidate_id}/apply` | Queue, detail, lifecycle, duplicate linking, deterministic report-scoped planning, and transactional resolution |
| Faculty | `GET /faculty/assignments`, `GET /faculty/timetable` | Own stable mappings and schedule |
| Faculty directory | `GET/POST /faculty-directory` | Paginated active-faculty lookup and coordinator/admin faculty provisioning |
| Faculty management | `GET/POST /faculty-assignments`, `DELETE /faculty-assignments/{id}` | Coordinator/admin class mapping |
| Notifications | `GET /notifications`, `PATCH /notifications/{id}/read`, `POST /notifications/read-all` | Paginated inbox and read state |
| Preferences/jobs | `GET/PUT /notification-preferences`, `POST /notification-jobs/process` | Reminder preferences and idempotent generator |
| Timetable | `GET/POST /timetable`, `GET/DELETE /timetable/{id}`, `PATCH /timetable/{id}/room`, `PATCH /timetable/{id}/time`, `POST /timetable/import` | Institutional timetable management |
| Clash analytics | `GET /clashes`, `/clashes/room-suggestions`, `/clashes/student-risk`, `/clashes/student-groups`, `/clashes/student-resolutions` | Structural and student-risk analysis |
| Clash actions | `POST /clashes/room/{id1}/{id2}/apply-best-fix`, `POST /clashes/student-groups/{id}/apply-best-fix` | Validated fixes |
| Optimizer | `GET /optimizer/global`, `POST /optimizer/global/apply-best`, `GET /optimizer/plan`, `POST /optimizer/plan/apply` | Global and multi-step planning/execution |
| History | `GET /changes`, undo/redo routes under `/changes` and `/student-schedule-changes`, `GET /audit-trail` | Change inspection and rollback |
| Executions | `GET /optimizer/executions`, `GET /optimizer/executions/{id}`, undo/redo routes | Grouped execution history and rollback |
| Operations | `GET /health`, `GET /ready` | Liveness and strict DB migration readiness |

## Key request contracts

- Login accepts exactly one of `identifier` or legacy `email`, plus `password`. `identifier` may be a canonical registration number or email. Faculty, coordinator, and admin email login remains supported.
- Student provision requires `registration_number`, `full_name`, `department`, `program`, `batch`, `current_semester`, and `section`; `email` is optional. A caller may provide a temporary password or receive a cryptographically generated value once in the creation response. Plaintext credentials are never persisted or logged.
- Student roster import accepts multipart CSV/XLSX. `dry_run=true` previews the all-row validation summary; any invalid/duplicate-in-file row prevents application. `update_existing=true` updates institutional academic fields by registration number without implicitly changing verification or activation state. Existing rows are duplicates by default.
- Provisioned users must change their temporary password, which invalidates the first token. A verified student must then complete `/account/student-profile` onboarding before enrollment, personal timetable, or clash-report operations.
- Enrollment create: `course_code`, `section`, `semester` (non-empty strings). Course and section identities are stored uppercase; semester casing is normalized consistently. Case-only variants are duplicates.
- Clash-report create: 2–10 unique positive `timetable_entry_ids`, optional `notes`, optional `evidence_reference`. The service independently rechecks active/verified/onboarded identity, active-term enrollment, personal-timetable ownership, current entry state, and real overlap. Exact repeat submissions return 409.
- Clash review: `status` plus terminal `resolution_note`; duplicate status also requires `duplicate_of_report_id`. Allowed transitions are `submitted -> under_review|rejected|duplicate` and `under_review -> resolved|rejected|duplicate`.
- Resolution-candidate query: optional report-owned `target_entry_id`, `limit` (1–100), and `include_rejected_limit` (0–100). The report must be open, belong to the active term, still reference current timetable entries, and still represent an overlap. Candidate generation never mutates the timetable.
- Resolution apply: `target_entry_id`, non-blank `resolution_note`, and `confirm_conditional`. The report must first be `under_review`. `CONDITIONALLY_SAFE` requires explicit confirmation; `INSUFFICIENT_DATA` and `REJECTED` can never be applied. The 24-character candidate ID is regenerated under the timetable write lock from live timetable, enrollment-evidence, and policy state; stale IDs return 409 without writes.
- Faculty assignment create: `faculty_user_id`, `course_code`, `section`, `semester`.
- Timetable time change: `day`, `start_time`, and `end_time`. Day/time values are normalized and the request is rejected if the destination creates a room/faculty clash or increases cohort risk.
- Notification preferences: nullable reminder minutes (`5|10|15|30`), daily-summary flag/time, schedule-change flag, clash-report-update flag.
- Timetable create uses the strict `TimetableEntryCreate` schema in OpenAPI. Unknown fields are rejected and all text limits match their database columns. Import accepts multipart CSV/XLSX with configured size/type validation.

## Stable response conventions

- Collection APIs added after Phase 4 expose explicit totals or lists as shown in OpenAPI.
- Timetable entries, enrollments, faculty assignments, clash reports, notifications, and scheduling history expose `term_id`. Current operational APIs default to the active term; archived rows remain readable but cannot be mutated.
- Student clash-report detail includes immutable server-attached registration number, name, email, department, program, batch, semester, section, term, conflict fingerprint, class-item snapshots, and ordered event history. Later edits to the live profile do not rewrite report evidence.
- `/clashes/student-risk` uses active verified `StudentEnrollment` rows to create confirmed weighted edges. `affected_student_count` is the real edge weight. Timetable-only fallback is labeled `timetable_inference` and can only be probable/possible; it is suppressed when complete enrollment coverage disproves the heuristic pair. The summary reports unmapped enrollment rows as data-quality issues.
- `/clash-reports/{id}/resolution-candidates` preserves actual class duration, evaluates current room/faculty/section clashes and enrollment-backed student conflicts, applies the published institutional policy, and hard-rejects unsafe moves before ranking. Accepted planning states are `SAFE`, `CONDITIONALLY_SAFE`, and `INSUFFICIENT_DATA`; missing enrollment, room assignment, or faculty assignment is never presented as safe. Scores include explicit components and are deterministic planning scores, not ML predictions. Candidate IDs include timetable, enrollment-evidence, and policy state so later execution can reject stale selections.
- Successful candidate execution moves exactly one timetable entry, rechecks the live result, resolves the report, records the actor/candidate/safety status and resolution note in `student_schedule_changes`, appends a report event, and creates schedule/report notifications in one transaction. Any failure rolls everything back. Linked undo reopens the report as `under_review`; redo revalidates the original candidate before resolving it again. Both append actor-attributed report events and notify the reporting student.
- Student schedule-change history exposes nullable `report_id`, `actor_user_id`, `candidate_id`, `safety_status`, and `report_resolution_note`. Legacy optimizer group changes keep `group_id`; report resolutions use `group_id=null`.
- Notifications contain parsed `payload`, `read_at`, and `created_at`; clients must use `type` for presentation behavior.
- `/dashboard` returns `{role, generated_for_day, data}`; `data` is role-specific and clients must branch on `role`.
- Clash, optimizer, execution, and history read endpoints publish their nested response schemas in OpenAPI. Mutation responses retain forward-compatible operation details while preserving the stable success/error envelope.

## Token handling

Access tokens are JWT bearer tokens with a configured lifetime. Store them using the platform's safest available mechanism, clear them on logout or 401, never place them in URLs, and never expose privileged tokens to logs. Password changes and account deactivation increment the account token version and immediately invalidate previously issued access tokens. The backend does not issue refresh tokens in contract version 0.12.0; clients return to login after expiry.
