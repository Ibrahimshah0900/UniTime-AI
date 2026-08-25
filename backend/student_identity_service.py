from __future__ import annotations

import secrets

from fastapi import HTTPException
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.auth_schemas import normalize_registration_number
from backend.auth_security import hash_password
from backend.models import StudentProfile, User
from backend.student_identity_schemas import (
    StudentIdentityUpdate,
    StudentOnboardingUpdate,
    StudentProvisionCreate,
)


def generate_temporary_password() -> str:
    # Generated with the operating system CSPRNG and returned only in the
    # provisioning response. It is never logged or persisted in plaintext.
    return secrets.token_urlsafe(18)


def serialize_student_identity(user: User, profile: StudentProfile) -> dict:
    return {
        "user_id": user.id,
        "registration_number": profile.registration_number,
        "full_name": user.full_name,
        "institutional_email": user.email,
        "department": profile.department,
        "program": profile.program,
        "batch": profile.batch,
        "current_semester": profile.current_semester,
        "section": profile.section,
        "academic_status": profile.academic_status,
        "is_verified": profile.is_verified,
        "is_active": user.is_active,
        "must_change_password": user.must_change_password,
        "preferred_name": profile.preferred_name,
        "onboarding_completed": profile.onboarding_completed,
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def get_student_identity(db: Session, user_id: int) -> dict:
    profile = db.get(StudentProfile, user_id)
    user = db.get(User, user_id)
    if profile is None or user is None or user.role != "student":
        raise HTTPException(status_code=404, detail="Student identity not found.")
    return serialize_student_identity(user, profile)


def _ensure_unique_identity(
    db: Session,
    *,
    registration_number: str,
    email: str | None,
    exclude_user_id: int | None = None,
) -> None:
    registration_query = select(StudentProfile.user_id).where(
        StudentProfile.registration_number == registration_number
    )
    if exclude_user_id is not None:
        registration_query = registration_query.where(
            StudentProfile.user_id != exclude_user_id
        )
    if db.scalar(registration_query) is not None:
        raise HTTPException(
            status_code=409,
            detail="A student with this registration number already exists.",
        )

    if email is not None:
        email_query = select(User.id).where(User.email == email)
        if exclude_user_id is not None:
            email_query = email_query.where(User.id != exclude_user_id)
        if db.scalar(email_query) is not None:
            raise HTTPException(
                status_code=409,
                detail="An account with this institutional email already exists.",
            )


def build_provisioned_student(
    db: Session,
    *,
    actor_user_id: int,
    request: StudentProvisionCreate,
    temporary_password: str,
) -> tuple[User, StudentProfile]:
    _ensure_unique_identity(
        db,
        registration_number=request.registration_number,
        email=request.email,
    )
    user = User(
        email=request.email,
        full_name=request.full_name,
        password_hash=hash_password(temporary_password),
        role="student",
        is_active=request.is_active,
        must_change_password=True,
    )
    db.add(user)
    db.flush()
    profile = StudentProfile(
        user_id=user.id,
        registration_number=request.registration_number,
        department=request.department,
        program=request.program,
        batch=request.batch,
        current_semester=request.current_semester,
        section=request.section,
        academic_status=request.academic_status.value,
        is_verified=request.is_verified,
        onboarding_completed=False,
        created_by_user_id=actor_user_id,
    )
    db.add(profile)
    db.flush()
    return user, profile


def provision_student(
    db: Session,
    *,
    actor_user_id: int,
    request: StudentProvisionCreate,
) -> dict:
    temporary_password = request.temporary_password or generate_temporary_password()
    try:
        user, profile = build_provisioned_student(
            db,
            actor_user_id=actor_user_id,
            request=request,
            temporary_password=temporary_password,
        )
        db.commit()
        db.refresh(user)
        db.refresh(profile)
    except HTTPException:
        db.rollback()
        raise
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The registration number or institutional email already exists.",
        ) from exc
    except Exception:
        db.rollback()
        raise
    return {
        "student": serialize_student_identity(user, profile),
        "temporary_password": temporary_password,
    }


def list_student_identities(
    db: Session,
    *,
    search: str | None = None,
    is_verified: bool | None = None,
    is_active: bool | None = None,
    offset: int = 0,
    limit: int = 50,
) -> dict:
    filters = [User.role == "student"]
    if is_verified is not None:
        filters.append(StudentProfile.is_verified.is_(is_verified))
    if is_active is not None:
        filters.append(User.is_active.is_(is_active))
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        filters.append(
            or_(
                StudentProfile.registration_number.ilike(pattern),
                User.full_name.ilike(pattern),
                User.email.ilike(pattern),
                StudentProfile.department.ilike(pattern),
                StudentProfile.program.ilike(pattern),
            )
        )
    joined = select(User, StudentProfile).join(
        StudentProfile,
        StudentProfile.user_id == User.id,
    ).where(*filters)
    total = db.scalar(
        select(func.count(User.id))
        .join(StudentProfile, StudentProfile.user_id == User.id)
        .where(*filters)
    ) or 0
    rows = db.execute(
        joined.order_by(StudentProfile.registration_number, User.id)
        .offset(offset)
        .limit(limit)
    ).all()
    return {
        "students": [serialize_student_identity(user, profile) for user, profile in rows],
        "total": total,
        "offset": offset,
        "limit": limit,
    }


def update_student_identity(
    db: Session,
    *,
    user_id: int,
    request: StudentIdentityUpdate,
) -> dict:
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    profile = db.scalar(
        select(StudentProfile)
        .where(StudentProfile.user_id == user_id)
        .with_for_update()
    )
    if user is None or profile is None or user.role != "student":
        raise HTTPException(status_code=404, detail="Student identity not found.")

    new_registration = request.registration_number or profile.registration_number
    new_email = request.email if "email" in request.model_fields_set else user.email
    _ensure_unique_identity(
        db,
        registration_number=new_registration,
        email=new_email,
        exclude_user_id=user.id,
    )

    if request.registration_number is not None:
        profile.registration_number = request.registration_number
    if request.full_name is not None:
        user.full_name = request.full_name
    if "email" in request.model_fields_set:
        user.email = request.email
    for field in ("department", "program", "batch", "current_semester", "section"):
        value = getattr(request, field)
        if value is not None:
            setattr(profile, field, value)
    if request.academic_status is not None:
        profile.academic_status = request.academic_status.value
    if request.is_verified is not None:
        profile.is_verified = request.is_verified
    if request.is_active is not None and request.is_active != user.is_active:
        user.is_active = request.is_active
        user.token_version += 1

    try:
        db.commit()
        db.refresh(user)
        db.refresh(profile)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="The registration number or institutional email already exists.",
        ) from exc
    except Exception:
        db.rollback()
        raise
    return serialize_student_identity(user, profile)


def reset_student_temporary_password(db: Session, *, user_id: int) -> dict:
    user = db.scalar(select(User).where(User.id == user_id).with_for_update())
    profile = db.get(StudentProfile, user_id)
    if user is None or profile is None or user.role != "student":
        raise HTTPException(status_code=404, detail="Student identity not found.")
    temporary_password = generate_temporary_password()
    user.password_hash = hash_password(temporary_password)
    user.must_change_password = True
    user.token_version += 1
    db.commit()
    return {
        "registration_number": profile.registration_number,
        "temporary_password": temporary_password,
        "must_change_password": True,
    }


def complete_student_onboarding(
    db: Session,
    *,
    user: User,
    request: StudentOnboardingUpdate,
) -> dict:
    if user.role != "student":
        raise HTTPException(status_code=403, detail="Only students have a student profile.")
    managed_user = db.get(User, user.id)
    profile = db.get(StudentProfile, user.id)
    if managed_user is None or profile is None:
        raise HTTPException(status_code=404, detail="Student identity not found.")
    if managed_user.must_change_password:
        raise HTTPException(
            status_code=409,
            detail="Change the temporary password before completing onboarding.",
        )
    profile.preferred_name = request.preferred_name
    profile.onboarding_completed = True
    db.commit()
    db.refresh(profile)
    return serialize_student_identity(managed_user, profile)

