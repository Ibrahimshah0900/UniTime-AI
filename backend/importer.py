from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import TimetableEntry
from backend.schemas import TimetableEntryCreate


REQUIRED_COLUMNS = {
    "course_code",
    "course_name",
    "semester",
    "section",
    "faculty",
    "room",
    "day",
    "start_time",
    "end_time",
}

OPTIONAL_COLUMNS = {
    "class_type",
}


COLUMN_ALIASES = {
    "course_code": {
        "course_code",
        "coursecode",
        "subject_code",
        "subjectcode",
        "code",
        "course_id",
        "courseid",
    },
    "course_name": {
        "course_name",
        "coursename",
        "course",
        "subject_name",
        "subjectname",
        "subject",
        "title",
    },
    "semester": {
        "semester",
        "sem",
        "semester_no",
        "semester_number",
        "semester_num",
    },
    "section": {
        "section",
        "sec",
        "class_section",
        "group",
    },
    "faculty": {
        "faculty",
        "faculty_name",
        "teacher",
        "teacher_name",
        "instructor",
        "instructor_name",
        "lecturer",
        "professor",
    },
    "room": {
        "room",
        "room_no",
        "room_number",
        "classroom",
        "class_room",
        "venue",
        "location",
    },
    "day": {
        "day",
        "weekday",
        "week_day",
    },
    "start_time": {
        "start_time",
        "start",
        "from_time",
        "time_from",
        "begin_time",
        "class_start",
    },
    "end_time": {
        "end_time",
        "end",
        "to_time",
        "time_to",
        "finish_time",
        "class_end",
    },
    "class_type": {
        "class_type",
        "type",
        "lecture_type",
        "session_type",
        "activity_type",
    },
}


def normalize_column_name(value: str) -> str:
    normalized = value.strip().lower()

    for character in (" ", "-", "/", "\\", ".", "(", ")", "[", "]"):
        normalized = normalized.replace(character, "_")

    while "__" in normalized:
        normalized = normalized.replace("__", "_")

    return normalized.strip("_")


def build_alias_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}

    for canonical_name, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            lookup[normalize_column_name(alias)] = canonical_name

    return lookup


ALIAS_LOOKUP = build_alias_lookup()


def map_column_name(column_name: str) -> str:
    normalized = normalize_column_name(column_name)

    return ALIAS_LOOKUP.get(
        normalized,
        normalized,
    )


def read_timetable_file(
    filename: str,
    content: bytes,
) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()

    try:
        if suffix == ".csv":
            return pd.read_csv(BytesIO(content))

        if suffix == ".xlsx":
            return pd.read_excel(
                BytesIO(content),
                engine="openpyxl",
            )

    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Could not read timetable file: {exc}",
        ) from exc

    raise HTTPException(
        status_code=400,
        detail="Only CSV and XLSX files are supported.",
    )


def entry_exists(
    db: Session,
    entry: TimetableEntryCreate,
) -> bool:
    statement = select(TimetableEntry).where(
        TimetableEntry.course_code == entry.course_code,
        TimetableEntry.course_name == entry.course_name,
        TimetableEntry.semester == entry.semester,
        TimetableEntry.section == entry.section,
        TimetableEntry.faculty == entry.faculty,
        TimetableEntry.room == entry.room,
        TimetableEntry.day == entry.day,
        TimetableEntry.start_time == entry.start_time,
        TimetableEntry.end_time == entry.end_time,
        TimetableEntry.class_type == entry.class_type,
    )

    return db.scalar(statement) is not None


def normalize_dataframe_columns(
    dataframe: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, str]]:
    original_columns = list(dataframe.columns)

    mapped_columns = [
        map_column_name(str(column))
        for column in original_columns
    ]

    duplicates = {
        column
        for column in mapped_columns
        if mapped_columns.count(column) > 1
    }

    if duplicates:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "Multiple uploaded columns map to the same "
                    "internal timetable field."
                ),
                "duplicate_mapped_columns": sorted(duplicates),
            },
        )

    dataframe = dataframe.copy()
    dataframe.columns = mapped_columns

    mapping = {
        str(original): mapped
        for original, mapped in zip(
            original_columns,
            mapped_columns,
        )
    }

    return dataframe, mapping


async def import_timetable_file(
    file: UploadFile,
    db: Session,
) -> dict:
    if not file.filename:
        raise HTTPException(
            status_code=400,
            detail="Uploaded file must have a filename.",
        )

    content = await file.read()

    dataframe = read_timetable_file(
        filename=file.filename,
        content=content,
    )

    dataframe, column_mapping = normalize_dataframe_columns(
        dataframe
    )

    missing_columns = REQUIRED_COLUMNS - set(dataframe.columns)

    if missing_columns:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Timetable file is missing required columns.",
                "missing_columns": sorted(missing_columns),
                "detected_columns": list(dataframe.columns),
                "column_mapping": column_mapping,
            },
        )

    rows_read = len(dataframe)
    imported = 0
    duplicates = 0
    invalid = 0
    errors: list[dict] = []

    for row_number, row in dataframe.iterrows():
        row_data = {
            column: row[column]
            for column in REQUIRED_COLUMNS | OPTIONAL_COLUMNS
            if column in dataframe.columns
        }

        cleaned_data: dict[str, str] = {}

        for key, value in row_data.items():
            if pd.isna(value):
                cleaned_data[key] = ""
            else:
                cleaned_data[key] = str(value).strip()

        if not cleaned_data.get("class_type"):
            cleaned_data["class_type"] = "lecture"

        try:
            validated_entry = TimetableEntryCreate(
                **cleaned_data
            )

        except ValidationError as exc:
            invalid += 1

            errors.append(
                {
                    "row": int(row_number) + 2,
                    "type": "validation_error",
                    "details": exc.errors(
                        include_url=False,
                        include_context=False,
                    ),
                }
            )

            continue

        if entry_exists(db, validated_entry):
            duplicates += 1
            continue

        db_entry = TimetableEntry(
            **validated_entry.model_dump()
        )

        db.add(db_entry)
        imported += 1

    db.commit()

    return {
        "filename": file.filename,
        "rows_read": rows_read,
        "imported": imported,
        "duplicates": duplicates,
        "invalid": invalid,
        "column_mapping": column_mapping,
        "errors": errors,
    }