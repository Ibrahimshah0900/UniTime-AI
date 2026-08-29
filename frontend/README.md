# UniTime-AI Frontend

Production-oriented React frontend for the existing UniTime-AI FastAPI backend.

## Stack

- React 19 + TypeScript
- Vite
- React Router
- Custom responsive design system (no paid UI dependencies)
- Lucide icons
- Vitest + React Testing Library

## Design direction

The interface follows the approved **role-adaptive hybrid** direction:

- Coordinator/Admin: full desktop operations sidebar and dense management workspaces.
- Faculty: compact academic workspace optimized for desktop/tablet.
- Student: mobile-first planner experience with bottom navigation on small screens.
- Shared visual system with role accents, warm neutral surfaces, restrained status colors, responsive timetable layouts, and no generic AI-chatbot visual treatment.

## Backend contract

The frontend targets UniTime-AI API contract `0.15.0` and the committed OpenAPI snapshot in `../docs/openapi.json`.

Key rules preserved:

- JWT Bearer authentication.
- No refresh-token behavior is invented.
- Tokens are held in `sessionStorage`, restored on reload with `GET /auth/me`, and cleared on logout/401.
- 401 and 403 are handled differently.
- Student-only, faculty-only, coordinator/admin and admin-only routes are reflected in the UI.
- No direct database access, Supabase, Firebase or replacement backend.
- Clash, optimizer, execution, and history screens use the typed nested API contracts published by the backend.

## Environment

Copy `.env.example` to `.env.local` if needed:

```bash
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_ALLOW_PUBLIC_STUDENT_REGISTRATION=1
```

For production, set `VITE_API_BASE_URL` to the deployed FastAPI origin and leave
`VITE_ALLOW_PUBLIC_STUDENT_REGISTRATION` unset (or set it to `0`). Institutional
students are provisioned by a coordinator or administrator and sign in with their
university-issued email or registration number.

## Development

```bash
npm install
npm run dev
```

## Verification

```bash
npm run typecheck
npm test
npm run build
npm run test:e2e
```

The E2E command starts a freshly migrated isolated SQLite API and Vite server, then exercises registration plus student, faculty, coordinator, and admin browser workflows. Google Chrome must be installed locally.

## Implemented role experiences

### Student

- University-issued email or registration-number login
- Public self-registration only when explicitly enabled for development
- First-login temporary-password change and institutional onboarding
- Role-aware dashboard
- Personal timetable
- Enrollment management
- Clash-report submission using 2–10 personal timetable entries
- Owned clash-report list/detail and audit timeline
- Notifications/read state
- Reminder preferences
- Profile/password management
- Mobile bottom navigation

### Faculty

- Login/session handling
- Faculty dashboard
- Own assignment mappings
- Faculty timetable
- Notifications/preferences
- Profile/password management

### Coordinator

- Operational dashboard
- Verified student provisioning, roster import, identity management, and temporary-password reset
- Institutional timetable CRUD/import/room changes
- Clash analytics and validated fix actions
- Student clash-report review and legal status transitions
- Faculty assignment management
- Global and multi-step optimizer controls
- Optimizer execution inspection and undo/redo
- Timetable/student change history and audit
- Notifications/job processing

### Admin

- Coordinator capabilities
- Admin user list/search/filter
- Create faculty/coordinator/admin staff accounts with explicit roles
- Update role, name and activation state

## Contract-aware limitations

The clash-report `evidence_reference` field is implemented as text because the backend contract exposes a nullable string, not report-evidence file upload.

## Folder layout

- `src/api` – centralized FastAPI client and endpoint modules
- `src/app` – route/navigation composition
- `src/components` – shared UI, timetable and data-inspector components
- `src/features/auth` – authenticated session state
- `src/layouts` – role-adaptive application shell
- `src/pages` – user-facing route screens
- `src/routes` – protected route handling
- `src/types` – API-aligned TypeScript models
- `src/utils` – formatting and timetable helpers
- `tests` – focused frontend tests
