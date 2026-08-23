import re
from datetime import datetime

from pydantic import ValidationError
from sqlalchemy import select

from backend.course_parser import parse_raw_course_entry
from backend.database import SessionLocal
from backend.docx_parser import extract_raw_timetable_records
from backend.models import TimetableEntry
from backend.schemas import TimetableEntryCreate


FILE_PATH = (
    r"data\Computing Undergraduate Timetable Fall Semester 2026.docx"
)


# ---------------------------------------------------------------------------
# TIME PATTERNS
# ---------------------------------------------------------------------------

TIME_RANGE_PATTERN = re.compile(
    r"^\s*(?P<start>\d{1,2}:\d{2}\s*(?:am|pm))"
    r"\s*-\s*"
    r"(?P<end>\d{1,2}:\d{2}\s*(?:am|pm))\s*$",
    re.IGNORECASE,
)


# Matches explicit times written inside a course entry, for example:
#
# AI232(A,C)-PFAI-AH-GP LAB 1 (10:00 - 1:00)
#
EXPLICIT_TIME_PATTERN = re.compile(
    r"\(\s*"
    r"(?P<start>\d{1,2}:\d{2})"
    r"\s*-\s*"
    r"(?P<end>\d{1,2}:\d{2})"
    r"\s*\)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# KNOWN SOURCE CORRECTIONS
# ---------------------------------------------------------------------------

KNOWN_SOURCE_CORRECTIONS = {
    "11:30pm - 01:00pm": "11:30am - 01:00pm",
    "08:30am 10:00am": "08:30am - 10:00am",
}


# ---------------------------------------------------------------------------
# GENERAL TIME HELPERS
# ---------------------------------------------------------------------------

def normalize_time_text(value: str) -> str:
    value = value.strip().lower()

    value = value.replace(
        "–",
        "-",
    )

    value = value.replace(
        "—",
        "-",
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value


def apply_known_source_correction(
    value: str,
) -> tuple[str, dict | None]:

    normalized = normalize_time_text(
        value
    )

    for source_value, corrected_value in (
        KNOWN_SOURCE_CORRECTIONS.items()
    ):

        if normalized == source_value.lower():

            return (
                corrected_value,
                {
                    "type": "source_time_correction",
                    "original": value,
                    "corrected": corrected_value,
                    "message": (
                        "Known malformed time header "
                        "in the source timetable was corrected "
                        "for database normalization."
                    ),
                },
            )

    return value, None


def convert_to_24_hour(
    value: str,
) -> str:

    parsed = datetime.strptime(
        value.strip().lower(),
        "%I:%M%p",
    )

    return parsed.strftime(
        "%H:%M"
    )


def parse_time_slot(
    value: str,
) -> tuple[str, str, dict | None]:

    corrected_value, warning = (
        apply_known_source_correction(
            value
        )
    )

    normalized = normalize_time_text(
        corrected_value
    )

    match = TIME_RANGE_PATTERN.match(
        normalized
    )

    if not match:

        raise ValueError(
            f"Could not parse time slot: {value}"
        )

    start_time = convert_to_24_hour(
        match.group("start")
    )

    end_time = convert_to_24_hour(
        match.group("end")
    )

    return (
        start_time,
        end_time,
        warning,
    )


# ---------------------------------------------------------------------------
# EXPLICIT COURSE-TIME OVERRIDES
# ---------------------------------------------------------------------------

def infer_academic_time(
    value: str,
    *,
    is_end: bool = False,
    start_minutes: int | None = None,
) -> str:

    hour_text, minute_text = (
        value.split(":")
    )

    hour = int(
        hour_text
    )

    minute = int(
        minute_text
    )

    if not 1 <= hour <= 12:

        raise ValueError(
            f"Invalid explicit hour: {value}"
        )

    if not 0 <= minute <= 59:

        raise ValueError(
            f"Invalid explicit minute: {value}"
        )

    # Build AM/PM possibilities.
    #
    # Example:
    # 10:00 -> 10:00 or 22:00
    # 1:00  -> 01:00 or 13:00

    if hour == 12:

        candidates = [
            12 * 60 + minute
        ]

    else:

        candidates = [
            hour * 60 + minute,
            (hour + 12) * 60 + minute,
        ]

    # Only consider reasonable university timetable hours.

    candidates = [
        candidate
        for candidate in candidates
        if (
            7 * 60
            <= candidate
            <= 18 * 60
        )
    ]

    if not candidates:

        raise ValueError(
            f"Could not infer academic time: {value}"
        )

    if (
        is_end
        and start_minutes is not None
    ):

        later_candidates = [
            candidate
            for candidate in candidates
            if candidate > start_minutes
        ]

        if not later_candidates:

            raise ValueError(
                f"End time {value} is not later "
                "than the inferred start time."
            )

        minutes = min(
            later_candidates
        )

    else:

        minutes = min(
            candidates
        )

    return (
        f"{minutes // 60:02d}:"
        f"{minutes % 60:02d}"
    )


def extract_explicit_time_override(
    raw_text: str,
) -> tuple[str, str] | None:

    match = EXPLICIT_TIME_PATTERN.search(
        raw_text
    )

    if not match:

        return None

    start_time = infer_academic_time(
        match.group("start")
    )

    start_hour, start_minute = map(
        int,
        start_time.split(":"),
    )

    start_minutes = (
        start_hour * 60
        + start_minute
    )

    end_time = infer_academic_time(
        match.group("end"),
        is_end=True,
        start_minutes=start_minutes,
    )

    return (
        start_time,
        end_time,
    )


# ---------------------------------------------------------------------------
# NORMALIZED ENTRY KEY
# ---------------------------------------------------------------------------

def build_entry_key(
    entry: TimetableEntryCreate,
) -> tuple:

    return (
        entry.entry_kind,
        entry.course_code,
        entry.course_name,
        entry.semester,
        entry.section,
        entry.faculty,
        entry.room,
        entry.day,
        entry.start_time,
        entry.end_time,
        entry.class_type,
        entry.raw_text,
        entry.source,
    )


# ---------------------------------------------------------------------------
# BUILD NORMALIZED TIMETABLE
# ---------------------------------------------------------------------------

def build_normalized_entries() -> tuple[
    list[TimetableEntryCreate],
    list[dict],
]:

    raw_records, docx_warnings = (
        extract_raw_timetable_records(
            FILE_PATH
        )
    )

    normalized_entries: list[
        TimetableEntryCreate
    ] = []

    # Important:
    # DOCX merged cells may cause the same class to appear more than once.
    #
    # We deduplicate AFTER:
    #
    # 1. parsing the course
    # 2. correcting the time
    # 3. applying explicit time overrides
    # 4. validating the schema
    #
    # This means two grid records that normalize to the exact same real
    # timetable entry are stored only once.

    seen_normalized_entries: set[
        tuple
    ] = set()

    warnings: list[dict] = [
        {
            "type": "docx_warning",
            **warning,
        }
        for warning in docx_warnings
    ]

    for record_number, record in enumerate(
        raw_records,
        start=1,
    ):

        parsed = parse_raw_course_entry(
            record["raw_text"]
        )

        # ---------------------------------------------------------------
        # TIME
        # ---------------------------------------------------------------

        try:

            (
                start_time,
                end_time,
                time_warning,
            ) = parse_time_slot(
                record["time_slot"]
            )

            # Check whether the actual course text contains its own time.
            #
            # Explicit course timing takes precedence over the DOCX grid.

            explicit_override = (
                extract_explicit_time_override(
                    record["raw_text"]
                )
            )

            if explicit_override:

                grid_start = start_time
                grid_end = end_time

                (
                    start_time,
                    end_time,
                ) = explicit_override

                warnings.append(
                    {
                        "type": "explicit_time_override",
                        "record_number": record_number,
                        "day": record["day"],
                        "raw_text": record["raw_text"],
                        "grid_time": (
                            f"{grid_start}-{grid_end}"
                        ),
                        "explicit_time": (
                            f"{start_time}-{end_time}"
                        ),
                    }
                )

        except ValueError as exc:

            warnings.append(
                {
                    "type": "time_parse_error",
                    "record_number": record_number,
                    "day": record["day"],
                    "time_slot": record["time_slot"],
                    "raw_text": record["raw_text"],
                    "message": str(exc),
                }
            )

            continue

        # ---------------------------------------------------------------
        # SOURCE TIME WARNING
        # ---------------------------------------------------------------

        if time_warning:

            warnings.append(
                {
                    **time_warning,
                    "record_number": record_number,
                    "day": record["day"],
                    "raw_text": record["raw_text"],
                }
            )

        # ---------------------------------------------------------------
        # BUILD SCHEMA DATA
        # ---------------------------------------------------------------

        entry_data = {

            "entry_kind": parsed[
                "entry_kind"
            ],

            "course_code": parsed[
                "course_code"
            ],

            "course_name": parsed[
                "course_name"
            ],

            "semester": parsed[
                "semester"
            ],

            "section": parsed[
                "section"
            ],

            "faculty": parsed[
                "faculty"
            ],

            "room": parsed[
                "room"
            ],

            "day": record[
                "day"
            ],

            "start_time": start_time,

            "end_time": end_time,

            "class_type": parsed[
                "class_type"
            ],

            "raw_text": parsed[
                "raw_text"
            ],

            "source": "docx",
        }

        # ---------------------------------------------------------------
        # PYDANTIC VALIDATION
        # ---------------------------------------------------------------

        try:

            validated = (
                TimetableEntryCreate(
                    **entry_data
                )
            )

        except ValidationError as exc:

            warnings.append(
                {
                    "type": "schema_validation_error",
                    "record_number": record_number,
                    "day": record["day"],
                    "time_slot": record["time_slot"],
                    "raw_text": record["raw_text"],
                    "details": exc.errors(
                        include_url=False,
                        include_context=False,
                    ),
                }
            )

            continue

        # ---------------------------------------------------------------
        # NORMALIZED DUPLICATE REMOVAL
        # ---------------------------------------------------------------

        normalized_key = build_entry_key(
            validated
        )

        if (
            normalized_key
            in seen_normalized_entries
        ):

            warnings.append(
                {
                    "type": "normalized_duplicate_removed",
                    "record_number": record_number,
                    "day": record["day"],
                    "raw_text": record["raw_text"],
                    "start_time": start_time,
                    "end_time": end_time,
                }
            )

            continue

        seen_normalized_entries.add(
            normalized_key
        )

        normalized_entries.append(
            validated
        )

    return (
        normalized_entries,
        warnings,
    )


# ---------------------------------------------------------------------------
# DATABASE DUPLICATE CHECK
# ---------------------------------------------------------------------------

def database_entry_exists(
    db,
    entry: TimetableEntryCreate,
) -> bool:

    statement = select(
        TimetableEntry
    ).where(

        TimetableEntry.entry_kind
        == entry.entry_kind,

        TimetableEntry.course_code
        == entry.course_code,

        TimetableEntry.course_name
        == entry.course_name,

        TimetableEntry.semester
        == entry.semester,

        TimetableEntry.section
        == entry.section,

        TimetableEntry.faculty
        == entry.faculty,

        TimetableEntry.room
        == entry.room,

        TimetableEntry.day
        == entry.day,

        TimetableEntry.start_time
        == entry.start_time,

        TimetableEntry.end_time
        == entry.end_time,

        TimetableEntry.class_type
        == entry.class_type,

        TimetableEntry.raw_text
        == entry.raw_text,

        TimetableEntry.source
        == entry.source,
    )

    return (
        db.scalar(statement)
        is not None
    )


# ---------------------------------------------------------------------------
# DATABASE IMPORT
# ---------------------------------------------------------------------------

def import_docx_into_database() -> dict:

    entries, warnings = (
        build_normalized_entries()
    )

    blocking_errors = [
        warning
        for warning in warnings
        if warning["type"]
        in {
            "time_parse_error",
            "schema_validation_error",
        }
    ]

    if blocking_errors:

        return {
            "success": False,
            "validated": len(entries),
            "imported": 0,
            "duplicates": 0,
            "blocking_errors": len(
                blocking_errors
            ),
            "warnings": warnings,
        }

    db = SessionLocal()

    imported = 0
    duplicates = 0

    try:

        for entry in entries:

            if database_entry_exists(
                db,
                entry,
            ):

                duplicates += 1

                continue

            db_entry = TimetableEntry(
                **entry.model_dump()
            )

            db.add(
                db_entry
            )

            imported += 1

        db.commit()

    except Exception:

        db.rollback()

        raise

    finally:

        db.close()

    return {
        "success": True,
        "validated": len(entries),
        "imported": imported,
        "duplicates": duplicates,
        "blocking_errors": 0,
        "warnings": len(warnings),
    }


# ---------------------------------------------------------------------------
# DRY-RUN REPORT
# ---------------------------------------------------------------------------

def print_dry_run() -> None:

    entries, warnings = (
        build_normalized_entries()
    )

    blocking_errors = [
        warning
        for warning in warnings
        if warning["type"]
        in {
            "time_parse_error",
            "schema_validation_error",
        }
    ]

    source_corrections = [
        warning
        for warning in warnings
        if warning["type"]
        == "source_time_correction"
    ]

    explicit_overrides = [
        warning
        for warning in warnings
        if warning["type"]
        == "explicit_time_override"
    ]

    removed_duplicates = [
        warning
        for warning in warnings
        if warning["type"]
        == "normalized_duplicate_removed"
    ]

    print(
        "=" * 80
    )

    print(
        "UNITIME AI - DOCX IMPORT DRY RUN"
    )

    print(
        "=" * 80
    )

    print()

    print(
        f"Validated unique entries: "
        f"{len(entries)}"
    )

    print(
        f"Blocking errors: "
        f"{len(blocking_errors)}"
    )

    print(
        f"Source-time corrections: "
        f"{len(source_corrections)}"
    )

    print(
        f"Explicit time overrides: "
        f"{len(explicit_overrides)}"
    )

    print(
        f"Normalized duplicates removed: "
        f"{len(removed_duplicates)}"
    )

    # ---------------------------------------------------------------
    # EXPLICIT OVERRIDES
    # ---------------------------------------------------------------

    print()

    print(
        "Explicit time overrides:"
    )

    print(
        "-" * 80
    )

    if not explicit_overrides:

        print(
            "None"
        )

    else:

        for warning in explicit_overrides:

            print(
                f"{warning['day']} | "
                f"{warning['grid_time']} -> "
                f"{warning['explicit_time']} | "
                f"{warning['raw_text']}"
            )

    # ---------------------------------------------------------------
    # REMOVED DUPLICATES
    # ---------------------------------------------------------------

    print()

    print(
        "Normalized duplicates removed:"
    )

    print(
        "-" * 80
    )

    if not removed_duplicates:

        print(
            "None"
        )

    else:

        for warning in removed_duplicates:

            print(
                f"{warning['day']} | "
                f"{warning['start_time']}-"
                f"{warning['end_time']} | "
                f"{warning['raw_text']}"
            )

    # ---------------------------------------------------------------
    # BLOCKING ERRORS
    # ---------------------------------------------------------------

    if blocking_errors:

        print()

        print(
            "BLOCKING ERRORS:"
        )

        print(
            "-" * 80
        )

        for warning in blocking_errors:

            print(
                warning
            )


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

if __name__ == "__main__":

    # IMPORTANT:
    #
    # Running:
    #
    # python -m backend.docx_importer
    #
    # performs a SAFE DRY RUN only.
    #
    # It does NOT modify the database.

    print_dry_run()