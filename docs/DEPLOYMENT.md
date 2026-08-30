# Backend deployment

## Required production environment

- `APP_ENV=production`
- `DATABASE_URL=postgresql+psycopg://...`
- `AUTH_SECRET_KEY`: unique random value of at least 32 characters
- `CORS_ORIGINS`: comma-separated deployed frontend origins; no wildcard
- `ALLOWED_HOSTS`: comma-separated deployed API hosts; no wildcard
- `APP_TIMEZONE`: valid IANA timezone, normally `Asia/Karachi`
- `AUTH_ACCESS_TOKEN_MINUTES`: positive integer
- `ALLOW_PUBLIC_STUDENT_REGISTRATION=false` (required in production)
- `MAX_TIMETABLE_UPLOAD_MB`: positive integer
- `LOG_LEVEL`: `INFO` or the deployment-specific level

Never commit production credentials. Configure them in the hosting platform's secret manager.

## Container lifecycle

Build with `docker build -t unitime-ai-api .`. The image runs as a non-root user, applies `alembic upgrade head`, then starts Uvicorn on `$PORT`.

The repository also includes `frontend/Dockerfile`, an unprivileged Nginx SPA configuration, and `compose.yaml` for a complete PostgreSQL/backend/notification-worker/frontend deployment. Set `POSTGRES_PASSWORD`, a random `AUTH_SECRET_KEY` of at least 32 characters, and `PUBLIC_FRONTEND_ORIGIN` to the real deployed frontend origin, then run `docker compose up --build`. Compose intentionally has no localhost production CORS fallback. The frontend is exposed on port 8080 by default and proxies same-origin `/api` requests to FastAPI.

Use one migration-running instance during deployments if the hosting platform starts multiple replicas simultaneously. After migrations complete, scale application replicas normally.

The current migration head is `f3c1b6a9d742`. The migration chain includes the institutional scheduling foundation and the PostgreSQL academic-term sequence repair. Always run `alembic upgrade head` rather than hard-coding a historical revision.

## Release checks

1. `python -m pytest tests -q`
2. `alembic check`
3. In `frontend`, run `npm run lint`, `npm run typecheck`, `npm test`, `npm run build`, and `npm run test:e2e`.
4. `git diff --check`
5. Build both backend and frontend containers.
6. Apply migrations against a staging PostgreSQL database.
7. Verify `/health` returns 200.
8. Verify `/ready` returns 200 and reports the expected migration head.
9. Run authenticated smoke tests for student, faculty, coordinator, and admin roles.
10. Verify the deployed frontend can reach same-origin `/api/ready`.
11. Verify production `/docs`, `/redoc`, and `/openapi.json` are disabled.

GitHub Actions performs the strict SQLite regression suite, an authenticated role-flow smoke test against PostgreSQL 17, frontend lint/type/unit/build checks, and the isolated five-role browser suite. The PostgreSQL job applies the complete migration chain before exercising admin, coordinator, faculty, and student API paths.

## Authentication edge protection

The application returns uniform login errors and uses versioned, expiring access tokens. Public registration must remain disabled in production; student and faculty accounts are created through authenticated institutional provisioning routes. Configure the production ingress or API gateway to rate-limit `/auth/login` per source address, while allowing ordinary authenticated API traffic separately. A practical starting point is 10 authentication attempts per minute with a small burst allowance; tune this to the institution's identity and support policies. Do not expose Uvicorn directly to the public internet without this edge control and TLS termination.

## Notification job

Run `python -m backend.notification_worker --once` every minute using the hosting platform's cron/scheduled-job facility. The command accesses the configured database directly, so no long-lived bearer token is needed. Alternatively, run `python -m backend.notification_worker --interval-seconds 60` as a separate worker process and configure the platform to restart it on failure. Do not run the continuous worker inside every API replica.

Generation is idempotent: class reminders and daily summaries use durable deduplication keys, so a retried run does not create duplicate notifications. `POST /notification-jobs/process` remains available for an authenticated coordinator/admin to trigger or test the same processor manually.

## Rollback

Application rollback should normally deploy the previous image while leaving forward-compatible migrations in place. Database downgrades are destructive and must first be rehearsed on a restored backup. Take a managed PostgreSQL backup before any migration that changes or removes existing columns.
