# UniTime-AI v0.1.0

UniTime-AI v0.1.0 is the first complete public project release.

## Highlights

- FastAPI + SQLAlchemy/Alembic backend.
- React/TypeScript/Vite web application.
- Capacitor Android source.
- Student, faculty, coordinator, and administrator workflows.
- Timetable import, clash reporting, coordinator resolution workflow, audit history, and undo.
- Deterministic timetable-safety engine.
- Experimental CatBoost `research-v1` learning-to-rank model for ordering already-safe/conditionally-safe resolution candidates.
- Synthetic demo-data generator and documented demo credentials.
- Real timetable CSV/XLSX import path.
- Comprehensive tests and GitHub Actions CI.

## AI safety design

AI is important to the resolution workflow, but it is intentionally subordinate to deterministic safety.

CatBoost cannot approve an unsafe candidate or execute a timetable mutation. Only candidates that pass the deterministic safety gate can be ranked by the model. Runtime ML failure falls back to deterministic ranking.

The included model is `EXPERIMENTAL_SYNTHETIC`; evaluation metrics are synthetic research evidence, not real-university accuracy claims.

## How to try it

See:

- `README.md`
- `docs/TEACHER_RUN_GUIDE.md`
- `docs/PROJECT_GUIDE.md`

The easiest evaluation path is the local web demo with generated synthetic data.

## Real timetable use

Synthetic data is optional. A reviewer can start from a fresh database, apply migrations, create an admin/coordinator account, and import a real timetable from CSV/XLSX.

## Android note

The source includes a Capacitor Android project. Historical APKs in the `android-test-v0.1.0` prerelease were development/network-specific test builds.

For a physical phone on another network, build the APK with the laptop's current LAN backend URL as documented in the README.

## CI

The release is intended to be cut only after the backend, PostgreSQL, frontend, and Android GitHub Actions jobs pass.
