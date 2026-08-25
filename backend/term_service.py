from __future__ import annotations

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.models import AcademicTerm
from backend.term_schemas import AcademicTermCreate


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _ensure_legacy_term(db: Session) -> AcademicTerm | None:
    if (db.scalar(select(func.count(AcademicTerm.id))) or 0) != 0:
        return None
    now = utc_now()
    legacy = AcademicTerm(
        code="LEGACY-IMPORTED",
        name="Legacy Imported Term",
        status="active",
        activated_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(legacy)
    db.flush()
    return legacy


def get_active_term(db: Session, *, lock: bool = False) -> AcademicTerm:
    statement = select(AcademicTerm).where(AcademicTerm.status == "active")
    if lock:
        statement = statement.with_for_update()
    active = db.scalar(statement)
    if active is not None:
        return active

    legacy = _ensure_legacy_term(db)
    if legacy is not None:
        return legacy

    raise HTTPException(
        status_code=409,
        detail="There is no active academic term. Activate a planning term first.",
    )


def get_term(db: Session, term_id: int, *, lock: bool = False) -> AcademicTerm:
    _ensure_legacy_term(db)
    statement = select(AcademicTerm).where(AcademicTerm.id == term_id)
    if lock:
        statement = statement.with_for_update()
    term = db.scalar(statement)
    if term is None:
        raise HTTPException(status_code=404, detail="Academic term not found.")
    return term


def resolve_term_for_write(
    db: Session,
    term_id: int | None = None,
    *,
    allow_planning: bool = True,
) -> AcademicTerm:
    term = get_active_term(db) if term_id is None else get_term(db, term_id)
    mutable_statuses = {"active", "planning"} if allow_planning else {"active"}
    if term.status not in mutable_statuses:
        raise HTTPException(
            status_code=409,
            detail="Archived academic terms are read-only.",
        )
    return term


def require_active_term_id(db: Session, term_id: int) -> AcademicTerm:
    term = get_term(db, term_id)
    if term.status != "active":
        raise HTTPException(
            status_code=409,
            detail="This operation is only allowed in the active academic term.",
        )
    return term


def list_academic_terms(db: Session) -> dict:
    legacy = _ensure_legacy_term(db)
    if legacy is not None:
        db.commit()
    terms = list(
        db.scalars(
            select(AcademicTerm).order_by(
                AcademicTerm.created_at.desc(),
                AcademicTerm.id.desc(),
            )
        ).all()
    )
    active_term_id = next(
        (term.id for term in terms if term.status == "active"),
        None,
    )
    return {
        "terms": terms,
        "total": len(terms),
        "active_term_id": active_term_id,
    }


def create_academic_term(
    db: Session,
    *,
    actor_user_id: int,
    request: AcademicTermCreate,
) -> AcademicTerm:
    _ensure_legacy_term(db)
    if db.scalar(select(AcademicTerm.id).where(AcademicTerm.code == request.code)):
        raise HTTPException(status_code=409, detail="An academic term with this code already exists.")
    term = AcademicTerm(
        **request.model_dump(),
        status="planning",
        created_by_user_id=actor_user_id,
    )
    db.add(term)
    try:
        db.commit()
        db.refresh(term)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An academic term with this code already exists.",
        ) from exc
    except Exception:
        db.rollback()
        raise
    return term


def activate_academic_term(db: Session, *, term_id: int) -> AcademicTerm:
    try:
        term = get_term(db, term_id, lock=True)
        if term.status != "planning":
            raise HTTPException(
                status_code=409,
                detail="Only a planning term can be activated.",
            )
        current = db.scalar(
            select(AcademicTerm)
            .where(AcademicTerm.status == "active")
            .with_for_update()
        )
        if current is not None:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Archive the current active term ({current.code}) before activating "
                    "another term."
                ),
            )
        term.status = "active"
        term.activated_at = utc_now()
        term.archived_at = None
        db.commit()
        db.refresh(term)
        return term
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Another academic term became active concurrently.",
        ) from exc
    except Exception:
        db.rollback()
        raise


def archive_academic_term(db: Session, *, term_id: int) -> AcademicTerm:
    try:
        term = get_term(db, term_id, lock=True)
        if term.status != "active":
            raise HTTPException(
                status_code=409,
                detail="Only the active academic term can be archived.",
            )
        term.status = "archived"
        term.archived_at = utc_now()
        db.commit()
        db.refresh(term)
        return term
    except Exception:
        db.rollback()
        raise
