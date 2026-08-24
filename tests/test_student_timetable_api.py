from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.auth_dependencies import get_current_user
from backend.auth_security import hash_password
from backend.database import Base, get_db
from backend.models import StudentEnrollment, TimetableEntry, User
from backend.student_routes import router as student_router


def create_context():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    app = FastAPI()
    app.include_router(student_router)
    def override_get_db():
        db = Session()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override_get_db
    return app, TestClient(app), Session


def seed_student_data(Session):
    with Session() as db:
        user = User(email="student@example.edu", full_name="Student User", password_hash=hash_password("Password123"), role="student", is_active=True)
        db.add(user)
        db.commit()
        db.refresh(user)
        db.add(StudentEnrollment(user_id=user.id, course_code="AI232", section="A", semester="Fall 2026"))
        db.add(TimetableEntry(course_code="AI232", course_name="Artificial Intelligence", section="A,C", semester=None, day="Monday", start_time="10:00", end_time="11:00"))
        db.add(TimetableEntry(course_code="AI232", course_name="Artificial Intelligence", section="B", semester=None, day="Tuesday", start_time="10:00", end_time="11:00"))
        db.commit()
        db.expunge(user)
        return user


def test_student_timetable_requires_authentication():
    app, client, _ = create_context()
    assert client.get("/student/timetable").status_code == 401


def test_non_student_cannot_access_student_timetable():
    app, client, _ = create_context()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1, role="coordinator", is_active=True)
    assert client.get("/student/timetable").status_code == 403


def test_student_receives_personal_timetable():
    app, client, Session = create_context()
    student = seed_student_data(Session)
    app.dependency_overrides[get_current_user] = lambda: student
    response = client.get("/student/timetable")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["course_code"] == "AI232"
    assert body[0]["section"] == "A,C"
