# UniTime-AI Complete Project Guide

## 1. Purpose

UniTime-AI is a university scheduling platform built to make timetable information easier to consume and timetable clashes safer to resolve.

The application is designed around several roles:

- **Student** - views a personal timetable and enrollments, receives notifications, and reports timetable clashes.
- **Faculty** - views teaching assignments/timetables and manages scheduling availability where authorized.
- **Coordinator** - reviews clash reports, inspects candidate resolutions, applies controlled timetable changes, and sees history/analytics.
- **Administrator** - manages privileged accounts, institutional configuration, and broader operational workflows.

The project supports both a web application and an Android client.

## 2. High-level architecture

```text
                    +------------------------+
                    |   React / TypeScript   |
                    |      Vite frontend     |
                    +-----------+------------+
                                |
                                | HTTP/JSON API
                                v
+----------------+    +---------+----------+    +----------------------+
| Capacitor      |--->| FastAPI backend    |--->| SQLAlchemy / Alembic |
| Android client |    | auth + services    |    | SQLite / PostgreSQL  |
+----------------+    +---------+----------+    +----------------------+
                                |
                                v
                    +-----------+------------+
                    | Scheduling + clash     |
                    | safety engine          |
                    +-----------+------------+
                                |
              eligible candidates only
                                |
                                v
                    +-----------+------------+
                    | CatBoost research-v1   |
                    | learning-to-rank model |
                    +------------------------+
```

The backend is the authoritative application layer. The web and Android clients call the same API.

## 3. Backend technology

The backend is written for Python 3.13.

Main technologies:

- **FastAPI** - HTTP API, dependency injection, request/response validation, development docs.
- **SQLAlchemy 2** - ORM and database access.
- **Alembic** - schema migrations. The migration history owns schema creation.
- **Pydantic** - data validation and schemas.
- **PyJWT** - bearer authentication tokens.
- **pwdlib with Argon2** - password hashing.
- **pandas / openpyxl / python-docx** - timetable and structured file processing.
- **psycopg** - PostgreSQL driver.
- **CatBoost** - experimental candidate-ranking model.

SQLite is convenient for local/demo use. PostgreSQL is supported for production-style concurrency and is exercised by CI smoke tests.

## 4. Frontend technology

The web UI is a React/TypeScript single-page application.

Main technologies:

- React 19
- TypeScript
- Vite
- React Router
- date-fns
- Motion
- Lucide React
- Vitest
- Playwright

The frontend contains role-aware navigation and pages for dashboards, timetables, students, academic terms, faculty assignments/availability, scheduling operations, reports, insights, notifications, and account administration.

API access is centralized through the frontend client layer. `VITE_API_BASE_URL` selects the backend URL at build/runtime configuration time.

## 5. Android application

The Android project is built with **Capacitor 8** from the same React frontend.

- Application ID: `com.unitimeai.mobile`
- Web bundle directory: `dist`
- Android/Gradle source is committed under `frontend/android`
- Local HTTP testing can explicitly enable cleartext/mixed-content development behavior
- Production-style hosted use should use HTTPS

Because the API URL is a frontend build variable, a physical-phone LAN build should be created using the laptop's current IPv4 address.

## 6. Database and migrations

Alembic owns the database schema.

Normal startup does not rely on `create_all()` to create production tables.

Typical local flow:

```powershell
python -m alembic upgrade head
python -m uvicorn backend.app:app --reload
```

The application supports:

- local SQLite;
- PostgreSQL through a `postgresql+psycopg://...` `DATABASE_URL`.

GitHub CI checks migration correctness and runs PostgreSQL smoke/concurrency tests.

## 7. Timetable import

The application can import timetable data from CSV or XLSX.

Required logical fields:

- course code
- course name
- semester
- section
- faculty
- room
- day
- start time
- end time

Class type is optional and defaults to `lecture`.

The importer normalizes a number of common column aliases, validates rows, counts duplicates/invalid records, and commits valid entries transactionally.

`docs/timetable_import_template.csv` is the starter template for a real timetable.

## 8. Synthetic demo data

The project includes an isolated synthetic-data generator for demonstrations and benchmarking.

The generator:

- requires an explicit `--confirm-synthetic` flag;
- requires a filename containing `demo` or `synthetic`;
- refuses the normal development database;
- refuses a non-empty target;
- creates clearly synthetic users, courses, rooms, enrollments, timetable entries, and intentional conflicts.

Example:

```powershell
python scripts/generate_synthetic_demo.py `
  --database data/unitime-demo.db `
  --students 32 `
  --faculty 8 `
  --rooms 8 `
  --confirm-synthetic
```

Demo credentials use the `synthetic.invalid` domain and the password `SyntheticDemoOnly!2026`.

Synthetic data is for demonstrations. It is not required for real timetable use.

## 9. AI: why it matters

AI is an important component of UniTime-AI because clash resolution can produce many technically possible alternatives. A coordinator should not have to inspect a long unstructured list manually.

The project therefore includes a **CatBoost learning-to-rank model** called `research-v1`.

Its job is to improve the ordering of already-eligible resolution candidates so that more useful candidates appear earlier.

This is intentionally different from allowing an ML model to decide timetable safety.

### Safety-first AI pipeline

1. Candidate time/room changes are generated.
2. Each move is simulated before modifying the live timetable.
3. Deterministic institutional and structural rules are evaluated.
4. Room conflicts are checked.
5. Faculty conflicts are checked.
6. Section conflicts are checked.
7. Enrollment-backed student conflicts are checked.
8. Other risk/evidence rules are evaluated.
9. Candidates failing hard constraints are rejected.
10. Only `SAFE` and `CONDITIONALLY_SAFE` candidates may be sent to CatBoost.
11. CatBoost assigns a bounded ranking score to improve ordering.
12. The selected candidate is revalidated under the write lock before execution.

The model cannot convert a rejected candidate into a safe candidate and cannot execute timetable mutations.

### Model artifact

The frozen model is stored in:

`backend/ai_ranker/research_v1/model.cbm`

The artifact directory also contains:

- a feature contract;
- a manifest/checksum/version contract;
- synthetic evaluation results;
- validation-selection evidence.

### Privacy boundary

The ranking feature contract is designed to be PII-free. The model is not supposed to receive student names, registration numbers, email addresses, user IDs, faculty identity, course identity, or section identity as personal identifiers.

### Runtime fallback

If the CatBoost model is missing, corrupt, incompatible, or fails to predict, UniTime-AI falls back to deterministic weighted ranking.

Therefore **timetable safety does not depend on the ML model being available**.

## 10. AI evaluation

The current model status is:

`EXPERIMENTAL_SYNTHETIC`

It was trained/evaluated using synthetic ranking labels.

Frozen synthetic test evidence:

| Metric | Deterministic | CatBoost research-v1 |
|---|---:|---:|
| NDCG | 0.9557 | 0.9894 |
| NDCG@3 | 0.9190 | 0.9810 |
| Top-1 ranking accuracy | 0.6733 | 0.9000 |
| Mean reciprocal rank | 0.8168 | 0.9475 |

These numbers demonstrate improved ranking on the locked synthetic test set. They must **not** be presented as real-university accuracy, coordinator success rate, or probability that a candidate is safe.

Detailed evidence is in `docs/AI_EVALUATION.md`.

## 11. Clash-resolution workflow

A typical workflow is:

1. a student sees a timetable conflict;
2. the student submits a report;
3. the coordinator opens the report queue;
4. the backend identifies the relevant timetable entries;
5. deterministic logic generates and safety-gates possible resolutions;
6. the AI ranker orders the eligible candidates;
7. the coordinator reviews evidence and chooses a candidate;
8. the application revalidates the action;
9. the timetable change is applied;
10. the action is recorded in history;
11. the coordinator can inspect/undo changes through controlled workflows.

The design keeps a human coordinator in control while using AI to reduce candidate-search effort.

## 12. Authentication and roles

The application uses bearer tokens for authenticated API requests.

Passwords are hashed with Argon2 through pwdlib.

Access is role-based, with endpoints and UI behavior adapted for students, faculty, coordinators, and administrators.

Production runtime validation rejects unsafe production configuration such as weak/default secrets, inappropriate registration settings, and invalid host/CORS configuration.

## 13. Notifications and operations

The repository contains notification/reminder support and a notification worker.

Operational features include:

- reminders;
- dashboards;
- report queues;
- clash analytics;
- data-quality diagnostics;
- change history;
- rollback/undo;
- institutional scheduling inputs and generation workflows.

## 14. Testing strategy

Backend tests use Pytest.

Frontend tests use Vitest and Playwright.

GitHub Actions performs four major qualification jobs:

1. **Backend**
   - migrations
   - migration consistency
   - full backend tests
   - diff checks
   - backend Docker build

2. **Frontend**
   - lint
   - TypeScript checking
   - unit/component tests
   - build
   - Playwright E2E
   - frontend Docker build

3. **PostgreSQL smoke**
   - migrations against PostgreSQL
   - live DB smoke/concurrency tests

4. **Android**
   - frontend Android build
   - Capacitor sync
   - Gradle test compilation
   - debug APK build

## 15. Local demonstration

For a teacher/reviewer, the fastest route is:

1. generate the isolated synthetic database;
2. start FastAPI;
3. start Vite;
4. sign in as the synthetic student/coordinator;
5. demonstrate timetable, clash report, candidates, apply/history/undo.

See `docs/TEACHER_RUN_GUIDE.md`.

## 16. Real timetable use

For a real timetable:

1. do **not** use the synthetic demo DB;
2. start with a clean database;
3. apply Alembic migrations;
4. bootstrap an admin/coordinator;
5. import the real timetable using CSV/XLSX;
6. provision the real user/enrollment data required by the institution;
7. run backend and frontend normally.

A continuously hosted cloud backend is not required for local evaluation.

## 17. Repository layout

```text
UniTime-AI/
|-- backend/                 FastAPI backend and domain services
|   `-- ai_ranker/           ranking interfaces and frozen research model
|-- frontend/                React/Vite frontend
|   `-- android/             Capacitor Android project
|-- migrations/              Alembic migration history
|-- scripts/                 data/evaluation/helper scripts
|-- tests/                   backend qualification tests
|-- docs/                    contracts, guides, evaluation, OpenAPI
|-- data/                    small project/sample timetable inputs
|-- .github/workflows/       CI
|-- Dockerfile
|-- compose.yaml
|-- requirements.txt
|-- requirements-dev.txt
|-- pyproject.toml
`-- README.md
```

## 18. How to extend the project safely

When modifying UniTime-AI:

1. inspect the existing implementation before adding code;
2. reuse existing services and patterns;
3. make the smallest correct change;
4. keep deterministic safety authoritative;
5. do not send PII into the ranking model;
6. add/update tests for behavior changes;
7. run backend and frontend qualification;
8. regenerate OpenAPI when API contracts change;
9. update documentation when configuration or run instructions change;
10. use a feature branch and merge only after CI passes.

## 19. Current limitations

- The included CatBoost model is synthetic-research evidence, not a real-university production model.
- Android local-LAN builds need the correct backend URL for the network on which they are used.
- A hosted backend is not bundled with the GitHub release.
- Institutional policies and real data quality will vary by university and must be configured/validated before operational use.

## 20. Key documents

- `README.md`
- `docs/TEACHER_RUN_GUIDE.md`
- `docs/API_CONTRACT.md`
- `docs/openapi.json`
- `docs/AI_EVALUATION.md`
- `docs/RANKER_CONTRACT.md`
- `docs/SYNTHETIC_DATA.md`
- `docs/LEARNING_EVENTS.md`
- `docs/DEPLOYMENT.md`
- `CHANGELOG.md`
