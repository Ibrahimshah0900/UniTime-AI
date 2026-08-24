# UniTime-AI

UniTime-AI is a full-stack university timetable and clash-resolution application for students, faculty, coordinators, and administrators. The FastAPI backend provides authentication/RBAC, timetable import and safe editing, clash analysis, optimizer execution and rollback, personal schedules, faculty assignments, clash reporting, notifications/reminders, dashboards, and account administration. The React/Vite frontend provides the corresponding role-adaptive user workflows.

## Local setup

1. Create and activate a Python virtual environment.
2. Install dependencies: `pip install -r requirements-dev.txt`
3. Copy `.env.example` to `.env` and set a development `AUTH_SECRET_KEY`.
4. Apply migrations: `alembic upgrade head`
5. Run tests: `python -m pytest tests -q`
6. Start the API: `python -m uvicorn backend.app:app --reload`
7. In `frontend`, run `npm install` and `npm run dev`.

Development documentation is available at `http://127.0.0.1:8000/docs`. The frontend defaults to `http://127.0.0.1:5173`. Strict readiness is at `/ready`; liveness is at `/health`.

## Database ownership

Alembic exclusively owns schema creation. Application startup never calls `create_all()`. Local development defaults to SQLite. Production uses `DATABASE_URL`, with PostgreSQL supported through `psycopg`:

`postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE`

Always run `alembic upgrade head` before starting a new application release. `/ready` fails while the database is not at the application migration head.

## Production

The repository includes a non-root Docker image and GitHub Actions backend CI. The image applies migrations before starting Uvicorn. Required production configuration and deployment checks are documented in `docs/DEPLOYMENT.md`.

For a complete local production-style stack, set `POSTGRES_PASSWORD` and `AUTH_SECRET_KEY`, then run `docker compose up --build`. This starts PostgreSQL, the API, one notification worker, and the built frontend on port 8080.

Run due reminders from a platform scheduler with `python -m backend.notification_worker --once`, or deploy the documented single continuous worker process.

## API contract

The human-readable contract and authorization matrix are in `docs/API_CONTRACT.md`. The committed machine-readable contract is `docs/openapi.json`; regenerate it with:

`python scripts/export_openapi.py`

## Privileged bootstrap

Before an admin UI is available, bootstrap the first privileged account with:

`python -m backend.create_user --email admin@example.edu --name "Admin User" --role admin`

The command prompts interactively for the password. After bootstrap, admins can manage accounts through `/admin/users`.
