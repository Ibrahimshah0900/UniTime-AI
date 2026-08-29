# UniTime-AI

UniTime-AI is a full-stack university timetable and clash-resolution application for students, faculty, coordinators, and administrators.

The backend uses FastAPI and SQLAlchemy. The frontend uses React/Vite and is also packaged for Android with Capacitor. The system supports timetable import and editing, role-based access, personal schedules, enrollments, clash reporting, coordinator review, deterministic safety checks, ranked resolution candidates, apply/undo history, notifications, diagnostics, and administrative workflows.

> **Two separate ways to run**
>
> - **Demo mode** â€” clearly labeled synthetic data. Recommended for teacher demonstrations, screenshots, videos, and evaluation.
> - **Real-data mode** â€” fresh database plus an actual institutional timetable. Synthetic data is **not required**.

## Technology

- Python 3.13
- FastAPI
- SQLAlchemy + Alembic
- SQLite for simple local use
- PostgreSQL supported through `psycopg`
- React 19 + TypeScript + Vite
- Capacitor Android
- CatBoost research-v1 ranking layer
- GitHub Actions CI

## Quick web demo

This is the easiest way to evaluate UniTime-AI and the recommended setup for recording a demonstration video.

### 1. Clone and install

```powershell
git clone --branch mobile/android-test-v0.1.0 https://github.com/Ibrahimshah0900/UniTime-AI.git
Set-Location UniTime-AI

py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

### 2. Create an isolated synthetic demo database

```powershell
python scripts/generate_synthetic_demo.py `
  --database data/unitime-demo.db `
  --students 32 `
  --faculty 8 `
  --rooms 8 `
  --confirm-synthetic
```

The generator refuses the normal development database and refuses a non-empty target.

Tell the backend to use the demo database in the current PowerShell session:

```powershell
$env:DATABASE_URL='sqlite:///./data/unitime-demo.db'
```

### 3. Start the API

```powershell
python -m uvicorn backend.app:app --reload
```

- API: `http://127.0.0.1:8000`
- Health: `http://127.0.0.1:8000/health`
- Readiness: `http://127.0.0.1:8000/ready`
- Development docs: `http://127.0.0.1:8000/docs`

### 4. Start the web frontend

Open a second PowerShell window:

```powershell
Set-Location UniTime-AI\frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:5173`.

### Demo accounts

These accounts exist **only in generated synthetic demo data**.

| Role | Login | Password |
|---|---|---|
| Coordinator | `demo.coordinator@synthetic.invalid` | `SyntheticDemoOnly!2026` |
| Student | `demo.student00001@synthetic.invalid` | `SyntheticDemoOnly!2026` |
| Faculty | `demo.faculty001@synthetic.invalid` | `SyntheticDemoOnly!2026` |

Do not reuse these credentials for real deployments.

## Using a real timetable

Synthetic data is not needed for real use. Use a **fresh database** for actual timetable data and never mix real institutional data with the generated demo database.

### 1. Return to the normal local database

Open a new PowerShell session, or remove the temporary demo override:

```powershell
Remove-Item Env:DATABASE_URL -ErrorAction SilentlyContinue
```

Local development then uses `data/unitime_ai.db` unless another `DATABASE_URL` is configured.

### 2. Apply migrations

```powershell
python -m alembic upgrade head
```

Alembic owns the schema.

### 3. Create the first privileged account

```powershell
python -m backend.create_user --email admin@example.edu --name "Admin User" --role admin
```

The command prompts for a password. Privileged users can then manage accounts through the application.

### 4. Run backend and frontend

Backend:

```powershell
python -m uvicorn backend.app:app --reload
```

Frontend:

```powershell
Set-Location frontend
npm ci
npm run dev
```

### 5. Import the real timetable

Coordinator/admin timetable import supports **CSV and XLSX**.

A starter template is included at `docs/timetable_import_template.csv`.

Required fields:

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

Example:

```csv
course_code,course_name,semester,section,faculty,room,day,start_time,end_time,class_type
CS101,Introduction to Computing,Semester 1,A,Dr Example,R101,Monday,08:30,10:00,lecture
```

Replace the sample row with the institution's real timetable before importing.

## Android

The Android client is built from the same React frontend with Capacitor.

### Existing downloadable test APK

The current `android-test-v0.1.0` prerelease contains APKs created for local-network testing. A LAN test APK can contain the laptop IP used when that APK was built.

Therefore an arbitrary user should **not assume the existing LAN APK will automatically discover their laptop**.

For a different laptop/network, build an APK using that laptop's current LAN IP.

### Build an APK for your own local backend

Put the Android phone and laptop on the same Wi-Fi/hotspot.

Find the laptop IPv4 address:

```powershell
ipconfig
```

Assume the laptop is `192.168.1.20`.

Start the backend so the phone can reach it:

```powershell
$env:ALLOWED_HOSTS='localhost,127.0.0.1,192.168.1.20'
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

Build the Android frontend:

```powershell
Set-Location frontend

$env:VITE_API_BASE_URL='http://192.168.1.20:8000'
$env:CAPACITOR_DEV_CLEARTEXT='1'

npm ci
npm run build
npx cap sync android

Set-Location android
.\gradlew.bat :app:assembleDebug
```

APK output:

`frontend/android/app/build/outputs/apk/debug/app-debug.apk`

Install it on the phone. The phone and laptop must remain on the same network while the local backend is running.

`CAPACITOR_DEV_CLEARTEXT=1` is for local HTTP testing only. A hosted backend should use HTTPS.

## Configuration

Copy `.env.example` to `.env` only when persistent local configuration is needed.

Portable SQLite:

```text
DATABASE_URL=sqlite:///./data/unitime_ai.db
```

PostgreSQL:

```text
DATABASE_URL=postgresql+psycopg://USER:PASSWORD@HOST:5432/DATABASE
```

Never commit real database passwords, authentication secrets, tokens, or production credentials.

## AI and safety boundary

The repository includes a frozen CatBoost `research-v1` ranker trained and evaluated on **synthetic labels only**.

The ML model does **not** decide whether a timetable change is safe.

1. Deterministic hard constraints evaluate candidate safety.
2. Only eligible `SAFE` / `CONDITIONALLY_SAFE` candidates may reach the research ranker.
3. CatBoost ranks those eligible candidates.
4. Model/schema/runtime failure falls back to deterministic ranking.
5. Rejected or insufficient-data candidates never become safe because of an ML score.

The model score is not a probability of safety and is not evidence of real-university accuracy.

See:

- `docs/RANKER_CONTRACT.md`
- `docs/AI_EVALUATION.md`
- `docs/LEARNING_EVENTS.md`
- `docs/SYNTHETIC_DATA.md`

## Suggested demonstration video

Use the **web application** with synthetic data for teacher/portfolio recording.

Recommended 3â€“5 minute flow:

1. Introduce UniTime-AI and the timetable-clash problem.
2. Student login: personal timetable and enrollments.
3. Show a clash/report.
4. Coordinator login.
5. Open report queue/detail.
6. Show resolution candidates.
7. Explain deterministic safety gating and AI ranking.
8. Apply a conditionally safe resolution.
9. Show the timetable change.
10. Show history and undo/redo.
11. End with GitHub and Android support.

For LinkedIn, cut the strongest 60â€“90 seconds from the longer recording.

Recording tips:

- 1080p
- maximize the browser
- hide bookmarks/personal tabs
- turn notifications off
- use synthetic data so no real student/faculty information appears
- keep terminal windows out of the final recording after startup
- do one dry run before recording

## Tests

Backend:

```powershell
python -m pytest tests -q
```

Frontend:

```powershell
Set-Location frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build
npm run test:e2e
```

GitHub Actions also runs backend tests, PostgreSQL smoke tests, frontend checks, and Android compilation/build.

## Documentation

- `docs/API_CONTRACT.md`
- `docs/openapi.json`
- `docs/DEPLOYMENT.md`
- `docs/RANKER_CONTRACT.md`
- `docs/AI_EVALUATION.md`
- `docs/LEARNING_EVENTS.md`
- `docs/SYNTHETIC_DATA.md`

## Privacy and data

Use synthetic data for public demos, screenshots, portfolio posts, and videos.

When testing with real institutional data:

- obtain the necessary permission;
- do not commit real timetable/student/faculty data to GitHub;
- do not put secrets in `.env.example`;
- keep real databases outside version control;
- avoid exposing personal student information in public recordings.

## Release model

GitHub is the source and distribution point for this project.

A reviewer can:

- run the web application locally;
- generate the synthetic demo dataset;
- start from a clean database and import a real CSV/XLSX timetable;
- build an Android APK against their own local backend;
- inspect the API, AI-evaluation, safety, and deployment documentation.

A continuously hosted cloud backend is **not required** for local evaluation.