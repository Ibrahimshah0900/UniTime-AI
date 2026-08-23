from backend.course_parser import (
    parse_raw_course_entry,
)


TEST_ENTRIES = [
    "MT112 (C)-CAL 1-GZ",
    "CS210 (B)-DSA-SF-GP LAB 3",
    "CS375(A)-MAD-DrST-GP LAB 1",
    "CS432 (B,C)-HCI-MBS-GP LAB 2",
    "CS390-IS-AA",
    "CS100-ITC-FH [Online] clash with english 1",
    "MG412-OB-TBA [J-310]",
]


for entry in TEST_ENTRIES:
    print("=" * 80)
    print(entry)

    parsed = parse_raw_course_entry(
        entry
    )

    for key, value in parsed.items():
        print(
            f"{key:12}: {value}"
        )