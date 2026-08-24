from __future__ import annotations
from pathlib import Path
from fastapi import HTTPException, UploadFile
from backend.config import MAX_TIMETABLE_UPLOAD_BYTES, MAX_TIMETABLE_UPLOAD_MB

ALLOWED_EXTENSIONS = {".csv", ".xlsx"}
ALLOWED_CONTENT_TYPES = {
    ".csv": {"text/csv", "application/csv", "text/plain", "application/vnd.ms-excel"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"},
}
GENERIC_CONTENT_TYPES = {"application/octet-stream"}

def validate_upload_filename(filename: str | None) -> tuple[str, str]:
    if filename is None or not filename.strip():
        raise HTTPException(400, "Uploaded file must have a filename.")
    name = filename.strip()
    if "\x00" in name or "/" in name or "\\" in name:
        raise HTTPException(400, "Uploaded filename is invalid.")
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(415, "Unsupported timetable file type. Only CSV and XLSX files are supported.")
    return name, suffix

def validate_content_type(*, suffix: str, content_type: str | None) -> None:
    if not content_type:
        return
    content_type = content_type.split(";", 1)[0].strip().lower()
    if not content_type or content_type in GENERIC_CONTENT_TYPES:
        return
    if content_type not in ALLOWED_CONTENT_TYPES[suffix]:
        raise HTTPException(415, "Uploaded file content type does not match the timetable file type.")

def validate_file_content(*, suffix: str, content: bytes) -> None:
    if not content:
        raise HTTPException(400, "Uploaded timetable file is empty.")
    if suffix == ".xlsx" and not content.startswith(b"PK"):
        raise HTTPException(400, "Uploaded XLSX file is not a valid Excel workbook.")
    if suffix == ".csv":
        sample = content[:4096]
        if b"\x00" in sample:
            raise HTTPException(400, "Uploaded CSV file appears to contain binary data.")
        if content.startswith(b"PK"):
            raise HTTPException(400, "Uploaded CSV file does not appear to contain CSV data.")

async def read_timetable_upload(file: UploadFile) -> tuple[str, bytes]:
    filename, suffix = validate_upload_filename(file.filename)
    validate_content_type(suffix=suffix, content_type=file.content_type)
    content = await file.read(MAX_TIMETABLE_UPLOAD_BYTES + 1)
    if len(content) > MAX_TIMETABLE_UPLOAD_BYTES:
        raise HTTPException(
            413,
            f"Timetable upload is too large. Maximum allowed size is {MAX_TIMETABLE_UPLOAD_MB} MB.",
        )
    validate_file_content(suffix=suffix, content=content)
    return filename, content
