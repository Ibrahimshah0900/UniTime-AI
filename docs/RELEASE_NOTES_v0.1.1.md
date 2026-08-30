# UniTime-AI v0.1.1

This patch release is the final repository-audit and maintenance pass over the v0.1.0 application.

## Application status

Application behavior is unchanged from the qualified v0.1.0 code. The patch aligns public documentation, repository hygiene, CI action versions, and release metadata.

## Audit fixes

- Updated the frontend README to API contract `0.18.0`.
- Updated deployment documentation to the actual Alembic head `f3c1b6a9d742`.
- Replaced stale machine-specific/historical `AGENTS.md` content with a current repository-maintenance guide.
- Removed committed Android Studio `.idea` project-state files and added IDE-state ignores.
- Updated GitHub Actions to supported Node-24-generation action majors.
- Aligned Python, frontend, and Android patch-version metadata to `0.1.1`.
- Clarified that the importer fixture contains an intentionally invalid row used for validation testing.

## AI

The AI architecture is unchanged.

The included CatBoost `research-v1` model remains `EXPERIMENTAL_SYNTHETIC`. It ranks only candidates that already passed deterministic safety checks, and it cannot override hard constraints. Model/runtime failure falls back to deterministic weighted ranking.

Synthetic evaluation results are research evidence, not claims of real-university production accuracy.

## Android artifact

The attached Android APK is the **CI/emulator debug build**.

It is compiled with:

`VITE_API_BASE_URL=http://10.0.2.2:8000`

That address is the Android Emulator alias for the host machine. It is **not a universal physical-phone backend address**.

For a physical phone, rebuild the Android client with the laptop's current LAN IPv4 address by following the README / teacher guide.

## Recommended evaluation

For a teacher/reviewer, the easiest and most portable evaluation remains the local web demo documented in:

- `README.md`
- `docs/TEACHER_RUN_GUIDE.md`
- `docs/PROJECT_GUIDE.md`

A fresh database plus CSV/XLSX timetable import is supported for real-data evaluation.
