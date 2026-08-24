# UniTime-AI backend API contract

Contract version: `0.7.0`

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

- Public: `POST /auth/register`, `POST /auth/login`, `/`, `/health`, `/ready`.
- Any authenticated role: `/auth/me`, `/account/*`, `/dashboard`, `/notifications*`, `/notification-preferences`.
- Student only: `/student/enrollments*`, `/student/timetable`, `/student/clash-reports*`.
- Faculty only: `/faculty/assignments`, `/faculty/timetable`.
- Coordinator/admin: institutional timetable CRUD/import, clash analytics and fixes, optimizer plans/actions/history, faculty assignment management, clash-report review, notification job processing, audit/change history.
- Admin only: `/admin/users*`.

## Endpoint groups

| Group | Methods and paths | Contract purpose |
|---|---|---|
| Authentication | `POST /auth/register`, `POST /auth/login`, `GET /auth/me` | Student registration, JWT login, current user |
| Account | `PATCH /account/profile`, `POST /account/change-password` | Own profile and password |
| Admin users | `GET/POST /admin/users`, `PATCH /admin/users/{user_id}` | Search/create/update roles and activation |
| Dashboard | `GET /dashboard` | Role-specific operational summary |
| Student enrollments | `GET/POST /student/enrollments`, `DELETE /student/enrollments/{id}` | Stable course/section/semester enrollment identity |
| Student timetable | `GET /student/timetable` | Personal classes derived from enrollments |
| Clash reports | `GET/POST /student/clash-reports`, `GET /student/clash-reports/{id}` | Submit and track owned reports |
| Clash review | `GET /clash-reports`, `GET/PATCH /clash-reports/{id}` | Queue, detail, lifecycle, resolution and duplicate linking |
| Faculty | `GET /faculty/assignments`, `GET /faculty/timetable` | Own stable mappings and schedule |
| Faculty directory | `GET /faculty-directory` | Paginated active-faculty lookup for coordinator/admin assignment workflows |
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

- Enrollment create: `course_code`, `section`, `semester` (non-empty strings). Course and section identities are stored uppercase; semester casing is normalized consistently. Case-only variants are duplicates.
- Clash-report create: 2–10 unique positive `timetable_entry_ids`, optional `notes`, optional `evidence_reference`. Every entry must belong to the student's personal timetable and at least one selected pair must overlap.
- Clash review: `status` plus terminal `resolution_note`; duplicate status also requires `duplicate_of_report_id`. Allowed transitions are `submitted -> under_review|rejected|duplicate` and `under_review -> resolved|rejected|duplicate`.
- Faculty assignment create: `faculty_user_id`, `course_code`, `section`, `semester`.
- Timetable time change: `day`, `start_time`, and `end_time`. Day/time values are normalized and the request is rejected if the destination creates a room/faculty clash or increases cohort risk.
- Notification preferences: nullable reminder minutes (`5|10|15|30`), daily-summary flag/time, schedule-change flag, clash-report-update flag.
- Timetable create uses the strict `TimetableEntryCreate` schema in OpenAPI. Unknown fields are rejected and all text limits match their database columns. Import accepts multipart CSV/XLSX with configured size/type validation.

## Stable response conventions

- Collection APIs added after Phase 4 expose explicit totals or lists as shown in OpenAPI.
- Student clash-report detail includes immutable `items` snapshots and ordered `events` audit history.
- Notifications contain parsed `payload`, `read_at`, and `created_at`; clients must use `type` for presentation behavior.
- `/dashboard` returns `{role, generated_for_day, data}`; `data` is role-specific and clients must branch on `role`.
- Clash, optimizer, execution, and history read endpoints publish their nested response schemas in OpenAPI. Mutation responses retain forward-compatible operation details while preserving the stable success/error envelope.

## Token handling

Access tokens are JWT bearer tokens with a configured lifetime. Store them using the platform's safest available mechanism, clear them on logout or 401, never place them in URLs, and never expose privileged tokens to logs. Password changes increment the account token version and immediately invalidate previously issued access tokens. The backend does not issue refresh tokens in contract version 0.7.0; clients return to login after expiry.
