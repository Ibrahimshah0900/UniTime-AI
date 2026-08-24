from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.schemas import RoomChangeRequest, TimetableEntryCreate


def valid_timetable_payload() -> dict:
    return {
        "course_code": " cs-101 ",
        "section": " a, b ",
        "semester": "FALL 2026",
        "day": "Monday",
        "start_time": "09:00",
        "end_time": "10:00",
    }


def test_timetable_identity_fields_are_canonicalized():
    entry = TimetableEntryCreate(**valid_timetable_payload())

    assert entry.course_code == "CS-101"
    assert entry.section == "A,B"
    assert entry.semester == "Fall 2026"


def test_timetable_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        TimetableEntryCreate(**valid_timetable_payload(), unexpected="ignored")


@pytest.mark.parametrize(
    ("field", "length"),
    [
        ("course_code", 51),
        ("course_name", 151),
        ("semester", 51),
        ("section", 51),
        ("faculty", 151),
        ("room", 151),
        ("raw_text", 501),
    ],
)
def test_timetable_text_lengths_match_database_columns(field: str, length: int):
    payload = valid_timetable_payload()
    payload[field] = "X" * length

    with pytest.raises(ValidationError):
        TimetableEntryCreate(**payload)


def test_room_change_is_strict_and_bounded():
    assert RoomChangeRequest(room="  J-301  ").room == "J-301"

    with pytest.raises(ValidationError):
        RoomChangeRequest(room=" ")
    with pytest.raises(ValidationError):
        RoomChangeRequest(room="J-301", unexpected=True)
    with pytest.raises(ValidationError):
        RoomChangeRequest(room="R" * 151)
