from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from backend.auth_dependencies import (
    require_coordinator_or_admin,
    require_faculty,
)
from backend.database import get_db
from backend.institutional_scheduling_schemas import (
    CourseOfferingCreate,
    CourseOfferingResponse,
    CourseOfferingUpdate,
    FacultyAvailabilityCreate,
    FacultyAvailabilityResponse,
    FacultyTeachingProfileUpdate,
    FacultyWorkloadResponse,
    ManagedFacultyAvailabilityCreate,
)
from backend.institutional_scheduling_service import (
    create_course_offering,
    create_faculty_availability,
    delete_course_offering,
    delete_faculty_availability,
    list_course_offerings,
    list_faculty_availability,
    list_faculty_workloads,
    set_faculty_designation,
    update_course_offering,
)
from backend.models import User


course_offering_router = APIRouter(
    prefix="/course-offerings",
    tags=["Course Offerings"],
)
faculty_profile_router = APIRouter(
    prefix="/faculty-teaching-profiles",
    tags=["Faculty Teaching Profiles"],
)
faculty_availability_management_router = APIRouter(
    prefix="/faculty-availability",
    tags=["Faculty Availability"],
)
faculty_self_availability_router = APIRouter(
    prefix="/faculty",
    tags=["Faculty"],
)


@course_offering_router.get("", response_model=list[CourseOfferingResponse])
def get_course_offerings(
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
    term_id: int | None = Query(default=None, gt=0),
):
    return list_course_offerings(db, term_id=term_id)


@course_offering_router.post("", response_model=CourseOfferingResponse, status_code=201)
def add_course_offering(
    request: CourseOfferingCreate,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
):
    return create_course_offering(
        db,
        actor_user_id=current_user.id,
        request=request,
    )


@course_offering_router.patch("/{offering_id}", response_model=CourseOfferingResponse)
def edit_course_offering(
    offering_id: int,
    request: CourseOfferingUpdate,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
):
    return update_course_offering(
        db,
        offering_id=offering_id,
        request=request,
    )


@course_offering_router.delete("/{offering_id}", status_code=204)
def remove_course_offering(
    offering_id: int,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
) -> Response:
    delete_course_offering(db, offering_id=offering_id)
    return Response(status_code=204)


@faculty_profile_router.get("", response_model=list[FacultyWorkloadResponse])
def get_faculty_workloads(
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
    term_id: int | None = Query(default=None, gt=0),
    faculty_user_id: int | None = Query(default=None, gt=0),
):
    return list_faculty_workloads(
        db,
        term_id=term_id,
        faculty_user_id=faculty_user_id,
    )


@faculty_profile_router.put(
    "/{faculty_user_id}",
    response_model=FacultyWorkloadResponse,
)
def put_faculty_teaching_profile(
    faculty_user_id: int,
    request: FacultyTeachingProfileUpdate,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
    term_id: int | None = Query(default=None, gt=0),
):
    set_faculty_designation(
        db,
        faculty_user_id=faculty_user_id,
        designation=request.designation,
    )
    return list_faculty_workloads(
        db,
        term_id=term_id,
        faculty_user_id=faculty_user_id,
    )[0]


@faculty_availability_management_router.get(
    "",
    response_model=list[FacultyAvailabilityResponse],
)
def get_managed_faculty_availability(
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    faculty_user_id: int = Query(gt=0),
    db: Session = Depends(get_db),
    term_id: int | None = Query(default=None, gt=0),
):
    return list_faculty_availability(
        db,
        faculty_user_id=faculty_user_id,
        term_id=term_id,
    )


@faculty_availability_management_router.post(
    "",
    response_model=FacultyAvailabilityResponse,
    status_code=201,
)
def add_managed_faculty_availability(
    request: ManagedFacultyAvailabilityCreate,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
):
    return create_faculty_availability(
        db,
        faculty_user_id=request.faculty_user_id,
        request=FacultyAvailabilityCreate(
            term_id=request.term_id,
            day=request.day,
            start_time=request.start_time,
            end_time=request.end_time,
        ),
    )


@faculty_availability_management_router.delete(
    "/{window_id}",
    status_code=204,
)
def remove_managed_faculty_availability(
    window_id: int,
    current_user: Annotated[User, Depends(require_coordinator_or_admin)],
    db: Session = Depends(get_db),
) -> Response:
    delete_faculty_availability(db, window_id=window_id)
    return Response(status_code=204)


@faculty_self_availability_router.get(
    "/availability",
    response_model=list[FacultyAvailabilityResponse],
)
def get_my_true_availability(
    current_user: Annotated[User, Depends(require_faculty)],
    db: Session = Depends(get_db),
    term_id: int | None = Query(default=None, gt=0),
):
    return list_faculty_availability(
        db,
        faculty_user_id=current_user.id,
        term_id=term_id,
    )


@faculty_self_availability_router.post(
    "/availability",
    response_model=FacultyAvailabilityResponse,
    status_code=201,
)
def add_my_true_availability(
    request: FacultyAvailabilityCreate,
    current_user: Annotated[User, Depends(require_faculty)],
    db: Session = Depends(get_db),
):
    return create_faculty_availability(
        db,
        faculty_user_id=current_user.id,
        request=request,
    )


@faculty_self_availability_router.delete(
    "/availability/{window_id}",
    status_code=204,
)
def remove_my_true_availability(
    window_id: int,
    current_user: Annotated[User, Depends(require_faculty)],
    db: Session = Depends(get_db),
) -> Response:
    delete_faculty_availability(
        db,
        window_id=window_id,
        faculty_user_id=current_user.id,
    )
    return Response(status_code=204)
