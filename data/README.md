# Data directory

This directory is for small development/test fixtures only.

## Public repository rule

Do **not** commit real institutional timetable files, student records, faculty records, credentials, exported databases, or other private university data here.

Use:

- `data/test_timetable.csv` for generic importer testing;
- `data/messy_timetable.csv` for alias/normalization testing;
- `docs/timetable_import_template.csv` as the starter template for a real timetable.

Real local data should remain outside version control. SQLite database files (`*.db`) and `.env` are already ignored by the repository.
