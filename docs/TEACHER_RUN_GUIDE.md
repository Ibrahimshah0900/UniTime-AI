# UniTime-AI Teacher / Reviewer Run Guide

This guide gives two ways to evaluate UniTime-AI:

1. **Synthetic demonstration mode** - fastest and recommended for evaluation.
2. **Real timetable mode** - fresh database plus the teacher/institution's actual timetable.

## A. Fast synthetic demo

### Requirements

- Git
- Python 3.13
- Node.js / npm

### Clone

```powershell
git clone https://github.com/Ibrahimshah0900/UniTime-AI.git
Set-Location UniTime-AI
```

### Backend environment

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

### Generate a synthetic demo database

```powershell
python scripts/generate_synthetic_demo.py `
  --database data/unitime-demo.db `
  --students 32 `
  --faculty 8 `
  --rooms 8 `
  --confirm-synthetic
```

### Select the demo database

```powershell
$env:APP_ENV='development'
$env:DATABASE_URL='sqlite:///./data/unitime-demo.db'
$env:AUTH_SECRET_KEY='local-demo-secret-change-me-123456789'
```

### Start backend

```powershell
python -m uvicorn backend.app:app --reload
```

### Start frontend

In another PowerShell window:

```powershell
Set-Location 'C:\path\to\UniTime-AI\frontend'
npm.cmd ci
npm.cmd run dev
```

Open:

`http://127.0.0.1:5173`

### Synthetic accounts

Student:

```text
demo.student00001@synthetic.invalid
SyntheticDemoOnly!2026
```

Coordinator:

```text
demo.coordinator@synthetic.invalid
SyntheticDemoOnly!2026
```

Faculty:

```text
demo.faculty001@synthetic.invalid
SyntheticDemoOnly!2026
```

### Suggested demo path

1. Student dashboard
2. Student timetable
3. Enrollments / clash
4. Clash report
5. Coordinator dashboard
6. Report queue
7. Resolution candidates
8. Explain deterministic safety + AI ranking
9. Apply a candidate
10. Show changed timetable
11. History / undo

## B. Using a real timetable

Synthetic data is not required.

### Fresh database

Do not point the real-data session at `unitime-demo.db`.

Use the normal local database or configure a separate database:

```powershell
$env:DATABASE_URL='sqlite:///./data/unitime_ai.db'
python -m alembic upgrade head
```

### Bootstrap first admin

```powershell
python -m backend.create_user --email admin@example.edu --name "Admin User" --role admin
```

Choose a real password when prompted.

### Start application

Backend:

```powershell
python -m uvicorn backend.app:app --reload
```

Frontend:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

### Import timetable

Use `docs/timetable_import_template.csv` as the column template.

The application accepts CSV and XLSX timetable uploads.

Replace the sample row with the actual institutional timetable before import.

## C. Android on a physical phone

The phone and laptop should be on the same Wi-Fi/hotspot for a local backend.

Find the laptop IPv4 address with:

```powershell
ipconfig
```

If the laptop IP is `192.168.1.20`:

```powershell
$env:ALLOWED_HOSTS='localhost,127.0.0.1,192.168.1.20'
python -m uvicorn backend.app:app --host 0.0.0.0 --port 8000
```

Build Android:

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

APK:

`frontend/android/app/build/outputs/apk/debug/app-debug.apk`

## D. AI explanation for evaluation

The most important point:

> UniTime-AI does not let ML decide timetable safety. Deterministic rules first reject unsafe candidates. The CatBoost model then ranks only the candidates that have already passed the safety gate.

The frozen `research-v1` CatBoost model was evaluated on synthetic labels. Its metrics demonstrate the ranking pipeline but are not claims of real-university accuracy.

Detailed evidence:

- `docs/AI_EVALUATION.md`
- `docs/RANKER_CONTRACT.md`

## E. Common Windows issue: npm.ps1 blocked

If PowerShell says `npm.ps1` cannot run because scripts are disabled, use:

```powershell
npm.cmd run dev
```

No execution-policy change is required.

## F. Stop the application

Press `Ctrl+C` in the frontend terminal and backend terminal.
