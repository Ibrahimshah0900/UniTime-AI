from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth_security import hash_password
from backend.database import Base
from backend.enrollment_schemas import EnrollmentCreate
from backend.enrollment_service import create_student_enrollment, get_student_timetable
from backend.models import TimetableEntry, User


def create_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_student(db):
    user = User(email="student@example.edu", full_name="Test Student", password_hash=hash_password("Password123"), role="student", is_active=True)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def add_entry(db, section, semester=None):
    entry = TimetableEntry(course_code="AI232", course_name="Artificial Intelligence", section=section, semester=semester, day="Monday", start_time="10:00", end_time="11:00")
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def test_section_matches_combined_and_shared_entries():
    Session = create_session()
    with Session() as db:
        student = create_student(db)
        create_student_enrollment(db, user_id=student.id, request=EnrollmentCreate(course_code="AI232", section="A", semester="Fall 2026"))
        combined = add_entry(db, "A,C")
        shared = add_entry(db, None)
        add_entry(db, "B")
        timetable = get_student_timetable(db, student.id)
        ids = {entry.id for entry in timetable}
        assert combined.id in ids
        assert shared.id in ids
        assert len(timetable) == 2


def test_semester_is_enforced_when_present():
    Session = create_session()
    with Session() as db:
        student = create_student(db)
        create_student_enrollment(db, user_id=student.id, request=EnrollmentCreate(course_code="AI232", section="A", semester="Fall 2026"))
        matching = add_entry(db, "A", "Fall 2026")
        add_entry(db, "A", "Spring 2026")
        timetable = get_student_timetable(db, student.id)
        assert [entry.id for entry in timetable] == [matching.id]
