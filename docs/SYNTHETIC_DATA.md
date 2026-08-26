# Synthetic/demo data

UniTime-AI includes an **isolated deterministic synthetic-data generator** for development, resolver benchmarking, demonstrations, and tests. Generated records are not university data and must never be represented as such.

## Safety boundary

The generator is a CLI-only development tool. It is never called during FastAPI startup and it refuses:

- the normal development database `data/unitime_ai.db`;
- non-SQLite targets;
- targets whose file name does not contain `demo` or `synthetic`;
- existing non-empty database files;
- generation without the explicit `--confirm-synthetic` acknowledgement;
- application databases containing users, enrollments, timetable entries, reports, notifications, or learning events.

A newly migrated database contains the migration bootstrap term `LEGACY-IMPORTED`; that schema-only bootstrap state is the sole permitted pre-existing application row. The generator converts it into a clearly named `DEMO-FALL-2026` active term before adding synthetic records.

Synthetic identity values use `DEMO` labels and the reserved `.invalid` email domain. The generator never reads real users to create synthetic identities.

## Generate a demo database

From the repository root on Windows:

```bat
.venv\Scripts\python.exe scripts\generate_synthetic_demo.py --database data\unitime-demo.db --confirm-synthetic --benchmark
```

Useful options:

```text
--seed INTEGER
--students 8..10000
--faculty 8..500
--rooms 4..500
--benchmark
```

A given configuration and seed produce the same academic identities, enrollments, timetable pattern, and intentional conflicts. Database row IDs are deterministic for a fresh database.

## Dataset shape

The default dataset contains:

- one clearly labeled synthetic active term;
- eight semester cohorts;
- sections A and B;
- synthetic students with verified/onboarded institutional profiles;
- synthetic faculty and faculty-class assignments;
- synthetic rooms represented through the existing timetable room field;
- four courses per semester;
- deterministic enrollments;
- at least one intentional enrollment-backed clash per semester/section.

The project does not currently have separate course-catalog or room-capacity tables. The generator therefore does not fabricate institutional capacity, eligibility, or equipment facts.

## Benchmark

`--benchmark` measures the existing deterministic enrollment-backed conflict analysis and safe-candidate generator against the generated dataset. Reported values are observed at runtime and include conflict edges, affected-student counts, candidates evaluated, actionable candidates, and elapsed milliseconds. No performance number is hardcoded or presented as a trained-model metric.

## Cleanup

Demo databases are generated artifacts and must not be committed. Delete a demo database manually when it is no longer needed.
