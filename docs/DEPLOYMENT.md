# Backend deployment

## Required production environment

- `APP_ENV=production`
- `DATABASE_URL=postgresql+psycopg://...`
- `AUTH_SECRET_KEY`: unique random value of at least 32 characters
- `CORS_ORIGINS`: comma-separated deployed frontend origins; no wildcard
- `ALLOWED_HOSTS`: comma-separated deployed API hosts; no wildcard
- `APP_TIMEZONE`: valid IANA timezone, normally `Asia/Karachi`
- `AUTH_ACCESS_TOKEN_MINUTES`: positive integer
- `MAX_TIMETABLE_UPLOAD_MB`: positive integer
- `LOG_LEVEL`: `INFO` or the deployment-specific level

Never commit production credentials. Configure them in the hosting platform's secret manager.

## Container lifecycle

Build with `docker build -t unitime-ai-api .`. The image runs as a non-root user, applies `alembic upgrade head`, then starts Uvicorn on `$PORT`.

Use one migration-running instance during deployments if the hosting platform starts multiple replicas simultaneously. After migrations complete, scale application replicas normally.

## Release checks

1. `python -m pytest tests -q`
2. `alembic check`
3. `git diff --check`
4. Build the container.
5. Apply migrations against a staging PostgreSQL database.
6. Verify `/health` returns 200.
7. Verify `/ready` returns 200 and reports the expected migration head.
8. Run authenticated smoke tests for student, faculty, coordinator, and admin roles.
9. Verify CORS from the deployed frontend origin.
10. Verify production `/docs`, `/redoc`, and `/openapi.json` are disabled.

## Notification job

Call `POST /notification-jobs/process` on a one-minute schedule using a coordinator/admin service account. Generation is idempotent: class reminders and daily summaries use durable deduplication keys. For a larger deployment, this endpoint can later be moved behind a private worker without changing persisted notification contracts.

## Rollback

Application rollback should normally deploy the previous image while leaving forward-compatible migrations in place. Database downgrades are destructive and must first be rehearsed on a restored backup. Take a managed PostgreSQL backup before any migration that changes or removes existing columns.
