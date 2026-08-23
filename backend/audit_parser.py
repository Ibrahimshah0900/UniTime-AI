from collections import Counter

from backend.course_parser import parse_raw_course_entry
from backend.docx_parser import extract_raw_timetable_records


FILE_PATH = (
    r"data\Computing Undergraduate Timetable Fall Semester 2026.docx"
)


def audit_parser() -> None:
    records, docx_warnings = extract_raw_timetable_records(
        FILE_PATH
    )

    parsed_records = []
    issues = []

    for index, record in enumerate(records, start=1):
        parsed = parse_raw_course_entry(
            record["raw_text"]
        )

        combined = {
            **record,
            **parsed,
        }

        parsed_records.append(combined)

        record_issues = []

        # Only normal course entries require a course code.
        if (
            parsed["entry_kind"] == "course"
            and not parsed["course_code"]
        ):
            record_issues.append(
                "missing_course_code"
            )

        if not parsed["course_name"]:
            record_issues.append(
                "missing_course_name"
            )

        if not parsed["faculty"]:
            record_issues.append(
                "missing_faculty"
            )

        if record_issues:
            issues.append(
                {
                    "record_number": index,
                    "issues": record_issues,
                    "record": combined,
                }
            )

    class_type_counts = Counter(
        record["class_type"]
        for record in parsed_records
    )

    entry_kind_counts = Counter(
        record["entry_kind"]
        for record in parsed_records
    )

    room_counts = Counter(
        "has_room"
        if record["room"]
        else "no_room"
        for record in parsed_records
    )

    section_counts = Counter(
        "has_section"
        if record["section"]
        else "no_section"
        for record in parsed_records
    )

    parsed_course_codes = sum(
        1
        for record in parsed_records
        if record["course_code"]
    )

    print("=" * 80)
    print("UNITIME AI - REAL TIMETABLE PARSER AUDIT")
    print("=" * 80)

    print()
    print(f"Raw records: {len(records)}")

    print(
        "Successfully parsed course codes: "
        f"{parsed_course_codes}"
    )

    print(
        f"Entries needing review: {len(issues)}"
    )

    print(
        f"DOCX warnings: {len(docx_warnings)}"
    )

    print()
    print("Entry kinds:")

    for key, value in entry_kind_counts.items():
        print(f"  {key}: {value}")

    print()
    print("Class types:")

    for key, value in class_type_counts.items():
        print(f"  {key}: {value}")

    print()
    print("Room information:")

    for key, value in room_counts.items():
        print(f"  {key}: {value}")

    print()
    print("Section information:")

    for key, value in section_counts.items():
        print(f"  {key}: {value}")

    print()
    print("First 20 parsed records:")
    print("-" * 80)

    for record in parsed_records[:20]:
        print(
            f"{record['day']:9} | "
            f"{record['time_slot']:22} | "
            f"{record['entry_kind']:13} | "
            f"{str(record['course_code']):12} | "
            f"{str(record['section']):7} | "
            f"{str(record['course_name']):15} | "
            f"{str(record['faculty']):8} | "
            f"{str(record['room']):12} | "
            f"{record['class_type']}"
        )

    if issues:
        print()
        print("Entries requiring review:")
        print("-" * 80)

        for issue in issues:
            record = issue["record"]

            print(
                f"#{issue['record_number']} "
                f"{issue['issues']}"
            )

            print(
                f"  Entry kind: "
                f"{record['entry_kind']}"
            )

            print(
                f"  Day: {record['day']}"
            )

            print(
                f"  Time: {record['time_slot']}"
            )

            print(
                f"  Raw: {record['raw_text']}"
            )

            print(
                f"  Parsed code: "
                f"{record['course_code']}"
            )

            print(
                f"  Parsed name: "
                f"{record['course_name']}"
            )

            print(
                f"  Parsed faculty: "
                f"{record['faculty']}"
            )

            print()


if __name__ == "__main__":
    audit_parser()