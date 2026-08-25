from __future__ import annotations

from io import BytesIO
from pathlib import Path

import pandas as pd
from fastapi import HTTPException, UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import MAX_TIMETABLE_UPLOAD_BYTES, MAX_TIMETABLE_UPLOAD_MB
from backend.logging_config import get_logger
from backend.models import StudentProfile, User
from backend.student_identity_schemas import StudentProvisionCreate
from backend.student_identity_service import (
    build_provisioned_student,
    generate_temporary_password,
)
from backend.upload_security import (
    validate_content_type,
    validate_file_content,
    validate_upload_filename,
)


logger = get_logger(__name__)

REQUIRED_COLUMNS = {
    "registration_number",
    "full_name",
    "department",
    "program",
    "batch",
    "current_semester",
    "section",
}
OPTIONAL_COLUMNS = {"email"}
COLUMN_ALIASES = {
    "registration_number": {
        "registration_number",
        "registration_no",
        "registration",
        "reg_no",
        "reg_number",
        "student_id",
    },
    "full_name": {"full_name", "student_name", "name"},
    "email": {"email", "institutional_email", "official_email", "student_email"},
    "department": {"department", "dept"},
    "program": {"program", "degree", "degree_program"},
    "batch": {"batch", "cohort"},
    "current_semester": {"current_semester", "semester", "semester_no", "sem"},
    "section": {"section", "sec"},
}


def _normalize_column(value: str) -> str:
    normalized = value.strip().lower()
    for character in (" ", "-", "/", "\\", ".", "(", ")", "[", "]"):
        normalized = normalized.replace(character, "_")
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_")


ALIAS_LOOKUP = {
    _normalize_column(alias): canonical
    for canonical, aliases in COLUMN_ALIASES.items()
    for alias in aliases
}


async def _read_upload(file: UploadFile) -> tuple[str, bytes]:
    filename, suffix = validate_upload_filename(file.filename)
    validate_content_type(suffix=suffix, content_type=file.content_type)
    content = await file.read(MAX_TIMETABLE_UPLOAD_BYTES + 1)
    if len(content) > MAX_TIMETABLE_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Roster upload is too large. Maximum allowed size is {MAX_TIMETABLE_UPLOAD_MB} MB.",
        )
    validate_file_content(suffix=suffix, content=content)
    return filename, content


def _read_dataframe(filename: str, content: bytes) -> pd.DataFrame:
    try:
        if Path(filename).suffix.lower() == ".csv":
            return pd.read_csv(BytesIO(content), dtype=object)
        return pd.read_excel(BytesIO(content), engine="openpyxl", dtype=object)
    except Exception as exc:
        logger.exception("Failed to parse student roster upload | filename=%s", filename)
        raise HTTPException(status_code=400, detail="Could not read student roster file.") from exc


def _prepare_dataframe(dataframe: pd.DataFrame) -> pd.DataFrame:
    original_columns = [str(column) for column in dataframe.columns]
    mapped_columns = [
        ALIAS_LOOKUP.get(_normalize_column(column), _normalize_column(column))
        for column in original_columns
    ]
    duplicates = sorted(
        {column for column in mapped_columns if mapped_columns.count(column) > 1}
    )
    if duplicates:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Multiple roster columns map to the same field.",
                "duplicate_mapped_columns": duplicates,
            },
        )
    missing = sorted(REQUIRED_COLUMNS - set(mapped_columns))
    if missing:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Student roster is missing required columns.",
                "missing_columns": missing,
                "detected_columns": mapped_columns,
            },
        )
    prepared = dataframe.copy()
    prepared.columns = mapped_columns
    if prepared.empty:
        raise HTTPException(status_code=400, detail="Student roster contains no data rows.")
    return prepared


def _cell_text(value: object) -> str:
    return "" if pd.isna(value) else str(value).strip()


def _semester_value(value: object) -> object:
    if pd.isna(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _validation_errors(row: int, exc: ValidationError) -> list[dict]:
    errors = []
    for detail in exc.errors(include_url=False, include_context=False, include_input=False):
        location = detail.get("loc", ())
        errors.append(
            {
                "row": row,
                "field": str(location[-1]) if location else None,
                "type": "validation_error",
                "message": detail["msg"],
            }
        )
    return errors


async def import_student_roster(
    file: UploadFile,
    db: Session,
    *,
    actor_user_id: int,
    dry_run: bool,
    update_existing: bool,
) -> dict:
    filename, content = await _read_upload(file)
    dataframe = _prepare_dataframe(_read_dataframe(filename, content))
    roster_includes_email = "email" in dataframe.columns
    requests: list[tuple[int, StudentProvisionCreate]] = []
    errors: list[dict] = []
    seen_registrations: dict[str, int] = {}
    seen_emails: dict[str, int] = {}

    for index, row in dataframe.iterrows():
        row_number = int(index) + 2
        raw = {
            column: _cell_text(row[column])
            for column in REQUIRED_COLUMNS | OPTIONAL_COLUMNS
            if column in dataframe.columns
        }
        raw["current_semester"] = _semester_value(row["current_semester"])
        try:
            request = StudentProvisionCreate(**raw)
        except ValidationError as exc:
            errors.extend(_validation_errors(row_number, exc))
            continue

        previous_row = seen_registrations.get(request.registration_number)
        if previous_row is not None:
            errors.append(
                {
                    "row": row_number,
                    "field": "registration_number",
                    "type": "duplicate_row",
                    "message": f"Registration number duplicates roster row {previous_row}.",
                }
            )
            continue
        seen_registrations[request.registration_number] = row_number
        if request.email is not None:
            previous_email_row = seen_emails.get(request.email)
            if previous_email_row is not None:
                errors.append(
                    {
                        "row": row_number,
                        "field": "email",
                        "type": "duplicate_row",
                        "message": f"Institutional email duplicates roster row {previous_email_row}.",
                    }
                )
                continue
            seen_emails[request.email] = row_number
        requests.append((row_number, request))

    existing_profiles = {
        profile.registration_number: profile
        for profile in db.scalars(
            select(StudentProfile).where(
                StudentProfile.registration_number.in_(seen_registrations)
            )
        ).all()
    }
    email_owners = {
        email: user_id
        for user_id, email in db.execute(
            select(User.id, User.email).where(User.email.in_(seen_emails))
        ).all()
        if email is not None
    }

    would_create = 0
    would_update = 0
    duplicates = 0
    actionable: list[tuple[StudentProvisionCreate, StudentProfile | None]] = []
    for row_number, request in requests:
        existing_profile = existing_profiles.get(request.registration_number)
        expected_user_id = existing_profile.user_id if existing_profile is not None else None
        if request.email is not None:
            email_owner = email_owners.get(request.email)
            if email_owner is not None and email_owner != expected_user_id:
                errors.append(
                    {
                        "row": row_number,
                        "field": "email",
                        "type": "conflict",
                        "message": "Institutional email belongs to another account.",
                    }
                )
                continue
        if existing_profile is not None:
            if update_existing:
                would_update += 1
                actionable.append((request, existing_profile))
            else:
                duplicates += 1
        else:
            would_create += 1
            actionable.append((request, None))

    invalid = len({error["row"] for error in errors if error["row"] is not None})
    can_apply = invalid == 0
    result = {
        "filename": filename,
        "rows_read": len(dataframe),
        "would_create": would_create,
        "would_update": would_update,
        "duplicates": duplicates,
        "invalid": invalid,
        "can_apply": can_apply,
        "applied": False,
        "dry_run": dry_run,
        "errors": errors,
        "credentials": [],
    }
    if dry_run or not can_apply:
        return result

    credentials = []
    try:
        for request, existing_profile in actionable:
            if existing_profile is None:
                temporary_password = generate_temporary_password()
                build_provisioned_student(
                    db,
                    actor_user_id=actor_user_id,
                    request=request,
                    temporary_password=temporary_password,
                )
                credentials.append(
                    {
                        "registration_number": request.registration_number,
                        "temporary_password": temporary_password,
                    }
                )
                continue

            user = db.get(User, existing_profile.user_id)
            if user is None or user.role != "student":
                raise RuntimeError("Roster identity refers to a missing student user.")
            user.full_name = request.full_name
            if roster_includes_email:
                user.email = request.email
            existing_profile.department = request.department
            existing_profile.program = request.program
            existing_profile.batch = request.batch
            existing_profile.current_semester = request.current_semester
            existing_profile.section = request.section
            existing_profile.academic_status = request.academic_status.value
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Roster import conflicted with an existing registration number or email.",
        ) from exc
    except Exception:
        db.rollback()
        raise

    result["applied"] = True
    result["credentials"] = credentials
    return result
