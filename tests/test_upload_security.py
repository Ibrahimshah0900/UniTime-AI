from __future__ import annotations
import asyncio
from io import BytesIO
import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers, UploadFile
from backend.config import MAX_TIMETABLE_UPLOAD_BYTES
from backend.importer import read_timetable_file
from backend.upload_security import read_timetable_upload, validate_upload_filename

def upload(name: str, data: bytes, mime: str) -> UploadFile:
    return UploadFile(filename=name, file=BytesIO(data), headers=Headers({"content-type": mime}))

def run(file: UploadFile):
    return asyncio.run(read_timetable_upload(file))

def test_valid_csv():
    name, data = run(upload("timetable.csv", b"a,b\n1,2\n", "text/csv"))
    assert name == "timetable.csv" and data

def test_missing_and_unsafe_filename():
    for name in (None, "", "../x.csv", "folder\\x.csv"):
        with pytest.raises(HTTPException) as exc:
            validate_upload_filename(name)
        assert exc.value.status_code == 400

def test_bad_extension_415():
    with pytest.raises(HTTPException) as exc:
        run(upload("x.exe", b"x", "application/octet-stream"))
    assert exc.value.status_code == 415

def test_mime_mismatch_415():
    with pytest.raises(HTTPException) as exc:
        run(upload("x.csv", b"a,b\n", "image/png"))
    assert exc.value.status_code == 415

def test_empty_400():
    with pytest.raises(HTTPException) as exc:
        run(upload("x.csv", b"", "text/csv"))
    assert exc.value.status_code == 400

def test_oversize_413():
    with pytest.raises(HTTPException) as exc:
        run(upload("x.csv", b"a" * (MAX_TIMETABLE_UPLOAD_BYTES + 1), "text/csv"))
    assert exc.value.status_code == 413

def test_fake_xlsx_and_binary_csv_400():
    cases = [
        upload("x.xlsx", b"not excel", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        upload("x.csv", b"abc\x00def", "text/csv"),
    ]
    for file in cases:
        with pytest.raises(HTTPException) as exc:
            run(file)
        assert exc.value.status_code == 400

def test_parser_error_is_sanitized():
    with pytest.raises(HTTPException) as exc:
        read_timetable_file("broken.csv", b"\xff\xfe\xff")
    assert exc.value.status_code == 400
    assert exc.value.detail == "Could not read timetable file."
