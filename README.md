# UniTime-AI

[![UniTime-AI CI](https://github.com/Ibrahimshah0900/UniTime-AI/actions/workflows/backend-ci.yml/badge.svg?branch=main)](https://github.com/Ibrahimshah0900/UniTime-AI/actions/workflows/backend-ci.yml)

**AI-assisted university timetable management and clash resolution for students, faculty, coordinators, and administrators.**

UniTime-AI combines a FastAPI backend, React/TypeScript web frontend, Capacitor Android client, deterministic timetable-safety rules, and an experimental CatBoost learning-to-rank model. The key design choice is that **AI helps rank good scheduling options, but deterministic rules remain authoritative for safety**.

- Latest release: https://github.com/Ibrahimshah0900/UniTime-AI/releases/latest
- Full project guide: [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md)
- Teacher/reviewer run guide: [`docs/TEACHER_RUN_GUIDE.md`](docs/TEACHER_RUN_GUIDE.md)
- AI evaluation: [`docs/AI_EVALUATION.md`](docs/AI_EVALUATION.md)
- API contract: [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md)
- Deployment notes: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)

## What the application does

UniTime-AI provides role-aware workflows for university scheduling:

- personal student timetables and enrollments;
- faculty assignments and availability;
- academic-term management;
- timetable CSV/XLSX import and safe editing;
- clash detection and student clash reporting;
- coordinator report queues and review workflows;
- deterministic candidate-safety checks;
- AI-ranked resolution candidates;
- controlled apply, audit history, and rollback/undo;
- notifications and reminders;
- institutional scheduling and timetable generation;
- data-quality and resolver analytics;
- account and role administration.

## AI is an important part of the system

UniTime-AI uses a frozen **CatBoost `research-v1` learning-to-rank model** to improve the ordering of timetable-resolution candidates.

The model does **not** decide whether a change is safe. The scheduling pipeline first runs deterministic hard checks for room, faculty, section, enrollment-backed student conflicts, institutional rules, and other structural constraints. Only candidates already classified as `SAFE` or `CONDITIONALLY_SAFE` can be ranked by CatBoost. Rejected candidates cannot be made safe by an ML score.

The current model artifact is included in the repository under `backend/ai_ranker/research_v1/`. It was trained and evaluated on **synthetic labels only**, so its published metrics demonstrate the ranking pipeline rather than real-university production accuracy. If the model cannot load or predict, the application falls back to deterministic weighted ranking without weakening timetable safety.

See [`docs/AI_EVALUATION.md`](docs/AI_EVALUATION.md) and [`docs/RANKER_CONTRACT.md`](docs/RANKER_CONTRACT.md).

## Technology stack

### Backend

- Python 3.13
- FastAPI
- SQLAlchemy 2
- Alembic migrations
- Pydantic
- PyJWT authentication
- pwdlib / Argon2 password hashing
- pandas + openpyxl + python-docx for timetable/data processing
- SQLite for simple local use
- PostgreSQL through psycopg for production-style use
- CatBoost for the experimental ranking model

### Frontend

- React 19
- TypeScript
- Vite
- React Router
- date-fns
- Motion
- Lucide React
- Vitest
- Playwright

### Android

- Capacitor 8
- Android/Gradle project generated from the same React frontend
- Application ID: `com.unitimeai.mobile`

### Quality / operations

- Pytest
- GitHub Actions
- PostgreSQL smoke testing
- frontend lint/typecheck/unit/E2E testing
- Android compile/build CI
- Docker and Docker Compose support

## Demo mode vs real-data mode

UniTime-AI deliberately keeps demonstration data separate from real institutional data.

### Demo mode

Use the synthetic generator for:

- teacher/reviewer demonstrations;
- screenshots and videos;
- safe experimentation;
- clash-resolution evaluation;
- portfolio demonstrations.

### Real-data mode

Synthetic data is **not required**.

For real use:

1. start with a fresh database;
2. apply Alembic migrations;
3. create the first privileged account;
4. import the institution's real timetable from CSV/XLSX;
5. create/provision the required users and enrollments;
6. run the application normally.

Do not mix a real institutional database with the generated demo database.

## Quick web demo

### Prerequisites

- Git
- Python 3.13
- Node.js 22 / npm

### 1. Clone

```powershell
git clone https://github.com/Ibrahimshah0900/UniTime-AI.git
Set-Location UniTime-AI
```

### 2. Python environment

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

### 3. Generate an isolated synthetic demo database

```powershell
python scripts/generate_synthetic_demo.py `
  --database data/unitime-demo.db `
  --students 32 `
  --faculty 8 `
  --rooms 8 `
  --confirm-synthetic
```

Set it for the current PowerShell session:

```powershell
$env:DATABASE_URL='sqlite:///./data/unitime-demo.db'
$env:APP_ENV='development'
$env:AUTH_SECRET_KEY='local-demo-secret-change-me-123456789'
```

### 4. Start the API

```powershell
python -m uvicorn backend.app:app --reload
```

Useful URLs:

- API: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/health`
- Readiness: `http://127.0.0.1:8000/ready`
- Development API docs: `http://127.0.0.1:8000/docs`

### 5. Start the frontend

Open a second terminal, change to the cloned repository root, then:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Open:

`http://127.0.0.1:5173`

### Demo credentials

These credentials exist only in generated synthetic demo data:

| Role | Login | Password |
|---|---|---|
| Coordinator | `demo.coordinator@synthetic.invalid` | `SyntheticDemoOnly!2026` |
| Student | `demo.student00001@synthetic.invalid` | `SyntheticDemoOnly!2026` |
| Faculty | `demo.faculty001@synthetic.invalid` | `SyntheticDemoOnly!2026` |

Never reuse these credentials for a real deployment.

## Running with a real timetable

Remove any demo database override:

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
```

Apply migrations:

```powershell
python -m alembic upgrade head
```

Create the first privileged account:

```powershell
python -m backend.create_user --email admin@example.edu --name "Admin User" --role admin
```

Then start backend/frontend and import the real timetable through the application.

A starter file is included at:

`docs/timetable_import_template.csv`

Required timetable fields:

- `course_code`
- `course_name`
- `semester`
- `section`
- `faculty`
- `room`
- `day`
- `start_time`
- `end_time`

Optional:

- `class_type` (defaults to `lecture`)

CSV and XLSX are supported, and common alternative column names are normalized by the importer.

## Android local testing

The Android client uses the same frontend through Capacitor.

The historical `android-test-v0.1.0` prerelease contains network-specific test APKs used during development. They should not be treated as universal production APKs.

For a physical phone on a new network, build the Android client against the laptop's current LAN address.

Example laptop IP: `192.168.1.20`

Backend:

```powershell
$env:ALLOWED_HOSTS='localhost,127.0.0.1,192.168.1.20'
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

Android build:

```powershell
Set-Location frontend

$env:VITE_API_BASE_URL='http://192.168.1.20:8000'
$env:CAPACITOR_DEV_CLEARTEXT='1'

npm.cmd ci
npm.cmd run build
npx.cmd cap sync android

Set-Location android
.\gradlew.bat :app:assembleDebug
```

APK output:

`frontend/android/app/build/outputs/apk/debug/app-debug.apk`

The phone and laptop must be on the same network while using a local backend.

`CAPACITOR_DEV_CLEARTEXT=1` is a local-development option. A hosted backend should use HTTPS.

## Configuration

Copy `.env.example` to `.env` only when persistent local configuration is needed.

Local SQLite:

```text
DATABASE_URL=sqlite:///./data/unitime_ai.db
```

PostgreSQL:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE
```

Never commit real passwords, tokens, database credentials, authentication secrets, or private institutional data.

## Testing

Backend:

```powershell
python -m pytest tests -q
```

Frontend:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run lint
npm.cmd run typecheck
npm.cmd test
npm.cmd run build
npm.cmd run test:e2e
```

GitHub Actions qualifies:

- backend tests;
- Alembic migration consistency;
- PostgreSQL smoke/concurrency behavior;
- frontend lint/typecheck/unit/E2E/build;
- backend/frontend Docker builds;
- Android compilation and debug APK build.

## Documentation

- [`docs/PROJECT_GUIDE.md`](docs/PROJECT_GUIDE.md) - architecture, technology, features, AI, data flow, testing, and maintenance
- [`docs/TEACHER_RUN_GUIDE.md`](docs/TEACHER_RUN_GUIDE.md) - quickest evaluation and real-timetable workflow
- [`docs/AI_EVALUATION.md`](docs/AI_EVALUATION.md) - synthetic ranking evaluation and safety boundaries
- [`docs/RANKER_CONTRACT.md`](docs/RANKER_CONTRACT.md) - ML feature/ranker contract and fallback policy
- [`docs/API_CONTRACT.md`](docs/API_CONTRACT.md) - API and authorization contract
- [`docs/openapi.json`](docs/openapi.json) - machine-readable OpenAPI contract
- [`docs/SYNTHETIC_DATA.md`](docs/SYNTHETIC_DATA.md) - synthetic dataset rules
- [`docs/LEARNING_EVENTS.md`](docs/LEARNING_EVENTS.md) - learning-event privacy/data contract
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) - deployment configuration
- [`CHANGELOG.md`](CHANGELOG.md) - release history

## Privacy and responsible use

Use synthetic data for public demos, screenshots, recordings, and portfolio posts.

For real institutional data:

- obtain permission before using student/faculty information;
- keep real databases outside version control;
- do not commit `.env` or secrets;
- avoid exposing personal data in public recordings;
- follow the institution's data-handling requirements.

## Distribution model

The GitHub repository is the source and distribution point for the project.

A reviewer can:

- run the full web application locally;
- generate synthetic demo data;
- import a real CSV/XLSX timetable into a fresh database;
- build the Android client for their own local backend;
- inspect the AI model artifact, evaluation, API contract, tests, and safety architecture.

A continuously hosted cloud backend is not required for local evaluation.
