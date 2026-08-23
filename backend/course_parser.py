import re
from typing import Optional


COURSE_CODE_PATTERN = re.compile(
    r"^(?P<code>[A-Za-z]{2,4}\d{2,3}(?:/[A-Za-z]{2,4}\d{2,3})?)"
)

SECTION_PATTERN = re.compile(
    r"^\s*\((?P<section>[^)]+)\)"
)

SPECIAL_EVENT_PATTERN = re.compile(
    r"^\((?P<semester>[^)]+)\)\s*-\s*"
    r"\((?P<section>[^)]+)\)\s*-\s*"
    r"(?P<name>.+?)\s*-\s*"
    r"(?P<faculty>[^-]+)\s*-\s*"
    r"(?P<room>.+)$",
    re.IGNORECASE,
)

EXPLICIT_TIME_PATTERN = re.compile(
    r"\(\s*\d{1,2}:\d{2}\s*"
    r"(?:am|pm)?\s*-\s*"
    r"\d{1,2}:\d{2}\s*"
    r"(?:am|pm)?\s*\)",
    re.IGNORECASE,
)

ROOM_PATTERNS = [
    re.compile(
        r"\bGP\s*LAB\s*\d+\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bHP\s*LAB(?:\s*\d+)?\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bDLD\s*LAB\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bJ\s*BLOCK\s*ROOM\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bJ-\d+\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bAUDITORIUM\b",
        re.IGNORECASE,
    ),
]

ONLINE_PATTERN = re.compile(
    r"\[\s*ONL(?:I|N)?NE\s*\]|\[\s*ONLINE\s*\]",
    re.IGNORECASE,
)

LAB_PATTERN = re.compile(
    r"\bLAB\b",
    re.IGNORECASE,
)

SPECIAL_NOTE_PATTERNS = [
    re.compile(
        r"\bclash with\b.*$",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bsame room for\b.*$",
        re.IGNORECASE,
    ),
]


def clean_text(value: str) -> str:
    value = value.replace("\xa0", " ")
    value = value.replace("–", "-")
    value = value.replace("—", "-")

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def normalize_room(value: str) -> str:
    room = clean_text(value).upper()

    # ---------------------------------------------------------
    # GP LAB normalization
    #
    # GP LAB3
    # GP LAB 3
    # GP   LAB   3
    #
    # all become:
    # GP LAB 3
    # ---------------------------------------------------------

    match = re.fullmatch(
        r"GP\s*LAB\s*(\d+)",
        room,
        flags=re.IGNORECASE,
    )

    if match:
        return (
            f"GP LAB {match.group(1)}"
        )

    # ---------------------------------------------------------
    # HP LAB normalization
    #
    # HP LAB3 -> HP LAB 3
    # HP LAB 3 -> HP LAB 3
    # ---------------------------------------------------------

    match = re.fullmatch(
        r"HP\s*LAB\s*(\d+)",
        room,
        flags=re.IGNORECASE,
    )

    if match:
        return (
            f"HP LAB {match.group(1)}"
        )

    if re.fullmatch(
        r"HP\s*LAB",
        room,
        flags=re.IGNORECASE,
    ):
        return "HP LAB"

    # ---------------------------------------------------------
    # DLD LAB
    # ---------------------------------------------------------

    if re.fullmatch(
        r"DLD\s*LAB",
        room,
        flags=re.IGNORECASE,
    ):
        return "DLD LAB"

    # ---------------------------------------------------------
    # J BLOCK ROOM
    # ---------------------------------------------------------

    if re.fullmatch(
        r"J\s*BLOCK\s*ROOM",
        room,
        flags=re.IGNORECASE,
    ):
        return "J BLOCK ROOM"

    # ---------------------------------------------------------
    # J block numbered rooms
    #
    # J-310 stays J-310
    # ---------------------------------------------------------

    match = re.fullmatch(
        r"J\s*-\s*(\d+)",
        room,
        flags=re.IGNORECASE,
    )

    if match:
        return (
            f"J-{match.group(1)}"
        )

    # ---------------------------------------------------------
    # Auditorium
    # ---------------------------------------------------------

    if re.fullmatch(
        r"AUDITORIUM",
        room,
        flags=re.IGNORECASE,
    ):
        return "AUDITORIUM"

    # If no known normalization is needed,
    # preserve the cleaned uppercase room value.
    return room


def parse_special_event(
    raw_text: str,
) -> Optional[dict]:
    match = SPECIAL_EVENT_PATTERN.match(
        raw_text
    )

    if not match:
        return None

    semester = clean_text(
        match.group("semester")
    )

    semester = re.sub(
        r"\s*Semester\s*$",
        "",
        semester,
        flags=re.IGNORECASE,
    )

    section = clean_text(
        match.group("section")
    )

    section = re.sub(
        r"\s+",
        "",
        section,
    )

    return {
        "entry_kind": "special_event",
        "course_code": None,
        "course_name": clean_text(
            match.group("name")
        ),
        "semester": semester,
        "section": section,
        "faculty": clean_text(
            match.group("faculty")
        ),
        "room": normalize_room(
            match.group("room")
        ),
        "class_type": "other",
        "note": None,
        "raw_text": raw_text,
    }


def extract_course_code(
    raw_text: str,
) -> tuple[Optional[str], str]:
    match = COURSE_CODE_PATTERN.match(
        raw_text
    )

    if not match:
        return None, raw_text

    course_code = match.group(
        "code"
    ).upper()

    remaining = raw_text[
        match.end():
    ].strip()

    return (
        course_code,
        remaining,
    )


def extract_section(
    remaining: str,
) -> tuple[Optional[str], str]:
    match = SECTION_PATTERN.match(
        remaining
    )

    if not match:
        return None, remaining

    section = match.group(
        "section"
    ).strip()

    section = re.sub(
        r"\s+",
        "",
        section,
    )

    remaining = remaining[
        match.end():
    ].strip()

    return (
        section,
        remaining,
    )


def extract_room(
    raw_text: str,
) -> Optional[str]:

    for pattern in ROOM_PATTERNS:

        match = pattern.search(
            raw_text
        )

        if match:

            return normalize_room(
                match.group(0)
            )

    if ONLINE_PATTERN.search(
        raw_text
    ):
        return "ONLINE"

    return None


def extract_class_type(
    raw_text: str,
) -> str:

    if ONLINE_PATTERN.search(
        raw_text
    ):
        return "online"

    if LAB_PATTERN.search(
        raw_text
    ):
        return "lab"

    return "lecture"


def extract_note(
    raw_text: str,
) -> Optional[str]:

    for pattern in SPECIAL_NOTE_PATTERNS:

        match = pattern.search(
            raw_text
        )

        if match:

            return clean_text(
                match.group(0)
            )

    return None


def strip_known_room_text(
    value: str,
) -> str:
    result = value

    for pattern in ROOM_PATTERNS:

        result = pattern.sub(
            "",
            result,
        )

    result = ONLINE_PATTERN.sub(
        "",
        result,
    )

    result = re.sub(
        r"\[\s*LAB\s+ONLINE\s*\]",
        "",
        result,
        flags=re.IGNORECASE,
    )

    # Remove empty brackets that may remain
    # after room text has been removed.
    #
    # Example:
    #
    # TBA [J-310]
    # ->
    # TBA []
    # ->
    # TBA

    result = re.sub(
        r"\[\s*\]",
        "",
        result,
    )

    return clean_text(
        result
    )


def parse_course_and_faculty(
    remaining: str,
) -> tuple[
    Optional[str],
    Optional[str],
]:
    value = remaining.strip()

    value = value.lstrip(
        "-"
    ).strip()

    if not value:
        return None, None

    # Remove explicit timing notes.
    #
    # Example:
    #
    # AI232(A,C)-PFAI-AH-GP LAB 1 (10:00 - 1:00)
    #
    # prevents "(10:00 - 1:00)" from being
    # interpreted as part of faculty/course text.

    value = EXPLICIT_TIME_PATTERN.sub(
        "",
        value,
    )

    value = strip_known_room_text(
        value
    )

    for pattern in SPECIAL_NOTE_PATTERNS:

        value = pattern.sub(
            "",
            value,
        )

    value = clean_text(
        value
    )

    if not value:
        return None, None

    parts = [
        part.strip()
        for part in value.split("-")
        if part.strip()
    ]

    if not parts:
        return None, None

    if len(parts) == 1:

        return (
            parts[0],
            None,
        )

    course_name = parts[0]

    faculty = parts[-1]

    if len(parts) > 2:

        middle = parts[
            1:-1
        ]

        if len(middle) == 1:

            faculty = parts[-1]

        else:

            course_name = "-".join(
                parts[:-1]
            )

    return (
        clean_text(
            course_name
        ),
        clean_text(
            faculty
        ),
    )


def parse_raw_course_entry(
    raw_text: str,
) -> dict:

    raw_text = clean_text(
        raw_text
    )

    # ---------------------------------------------------------
    # SPECIAL EVENT
    # ---------------------------------------------------------

    special_event = parse_special_event(
        raw_text
    )

    if special_event:

        return special_event

    # ---------------------------------------------------------
    # NORMAL COURSE
    # ---------------------------------------------------------

    course_code, remaining = (
        extract_course_code(
            raw_text
        )
    )

    section, remaining = (
        extract_section(
            remaining
        )
    )

    room = extract_room(
        raw_text
    )

    class_type = (
        extract_class_type(
            raw_text
        )
    )

    note = extract_note(
        raw_text
    )

    course_name, faculty = (
        parse_course_and_faculty(
            remaining
        )
    )

    return {
        "entry_kind": "course",
        "course_code": course_code,
        "course_name": course_name,
        "semester": None,
        "section": section,
        "faculty": faculty,
        "room": room,
        "class_type": class_type,
        "note": note,
        "raw_text": raw_text,
    }