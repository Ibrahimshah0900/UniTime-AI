from __future__ import annotations

import pytest

import backend.account_service as account_service
import backend.enrollment_service as enrollment_service
import backend.faculty_service as faculty_service
import backend.institutional_scheduling_service as institutional_scheduling_service
import backend.term_service as term_service


class SharedSchedulingLockReached(Exception):
    pass


MUTATION_CASES = (
    pytest.param(
        institutional_scheduling_service,
        "create_course_offering",
        {"actor_user_id": 1, "request": None},
        id="create-course-offering",
    ),
    pytest.param(
        institutional_scheduling_service,
        "update_course_offering",
        {"offering_id": 1, "request": None},
        id="update-course-offering",
    ),
    pytest.param(
        institutional_scheduling_service,
        "delete_course_offering",
        {"offering_id": 1},
        id="delete-course-offering",
    ),
    pytest.param(
        institutional_scheduling_service,
        "set_faculty_designation",
        {"faculty_user_id": 1, "designation": "lecturer"},
        id="set-faculty-designation",
    ),
    pytest.param(
        institutional_scheduling_service,
        "create_faculty_availability",
        {"faculty_user_id": 1, "request": None},
        id="create-faculty-availability",
    ),
    pytest.param(
        institutional_scheduling_service,
        "delete_faculty_availability",
        {"window_id": 1},
        id="delete-faculty-availability",
    ),
    pytest.param(
        faculty_service,
        "create_faculty_assignment",
        {"created_by_user_id": 1, "request": None},
        id="create-faculty-assignment",
    ),
    pytest.param(
        faculty_service,
        "delete_faculty_assignment",
        {"assignment_id": 1},
        id="delete-faculty-assignment",
    ),
    pytest.param(
        term_service,
        "activate_academic_term",
        {"term_id": 1},
        id="activate-term",
    ),
    pytest.param(
        term_service,
        "archive_academic_term",
        {"term_id": 1},
        id="archive-term",
    ),
    pytest.param(
        enrollment_service,
        "create_student_enrollment",
        {"user_id": 1, "request": None},
        id="create-enrollment",
    ),
    pytest.param(
        enrollment_service,
        "delete_student_enrollment",
        {"user_id": 1, "enrollment_id": 1},
        id="delete-enrollment",
    ),
    pytest.param(
        account_service,
        "update_profile",
        {"user": None, "request": None},
        id="update-profile",
    ),
    pytest.param(
        account_service,
        "update_admin_managed_user",
        {"actor": None, "target_user_id": 1, "request": None},
        id="update-admin-managed-user",
    ),
)


@pytest.mark.parametrize(
    ("module", "function_name", "kwargs"),
    MUTATION_CASES,
)
def test_scheduling_input_mutations_take_shared_lock_before_validation(
    monkeypatch,
    module,
    function_name,
    kwargs,
):
    db = object()

    def stop_at_lock(session):
        assert session is db
        raise SharedSchedulingLockReached

    monkeypatch.setattr(
        module,
        "acquire_timetable_write_lock",
        stop_at_lock,
    )

    with pytest.raises(SharedSchedulingLockReached):
        getattr(module, function_name)(db, **kwargs)
