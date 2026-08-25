from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    UploadFile,
)
from uuid import uuid4
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import ALLOWED_HOSTS, CORS_ORIGINS
from backend.logging_config import configure_logging, get_logger
from backend.notification_routes import job_router as notification_job_router
from backend.notification_routes import router as notification_router
from backend.notification_service import add_schedule_change_notifications
from backend.readiness import check_readiness
from backend.runtime_config import (
    api_documentation_settings,
    validate_runtime_config,
)
from backend.api_middleware import register_api_middleware
from backend.api_errors import register_api_error_handlers
from backend.account_routes import account_router, admin_router
from backend.auth_dependencies import require_coordinator_or_admin
from backend.auth_routes import router as auth_router
from backend.clash_report_routes import review_router as clash_report_review_router
from backend.clash_report_routes import student_router as student_clash_report_router
from backend.enrollment_routes import router as enrollment_router
from backend.dashboard_routes import router as dashboard_router
from backend.faculty_routes import faculty_router
from backend.faculty_routes import directory_router as faculty_directory_router
from backend.faculty_routes import management_router as faculty_management_router
from backend.student_routes import router as student_router
from backend.student_identity_routes import (
    account_router as student_identity_account_router,
    management_router as student_identity_management_router,
)
from backend.term_routes import router as academic_term_router
from backend.clash_detector import detect_clashes
from backend.course_parser import normalize_room
from backend.concurrency import acquire_timetable_write_lock
from backend.database import Base, engine, get_db
from backend.global_optimizer import (
    optimize_timetable_globally,
)
from backend.global_optimizer_applier import apply_global_best_move
from backend.multi_step_optimizer import build_multi_step_optimization_plan
from backend.multi_step_execution_service import apply_multi_step_plan_with_history
from backend.optimizer_execution_rollback import (
    redo_optimizer_execution,
    undo_optimizer_execution,
)
from backend.optimizer_execution_reader import (
    get_optimizer_execution_detail,
    list_optimizer_executions,
)
from backend.multi_step_plan_applier import apply_multi_step_optimization_plan
from backend.importer import import_timetable_file
from backend.models import (
    TimetableChange,
    TimetableEntry,
)
from backend.operation_schemas import (
    AuditTrailResponse,
    ChangeCollectionResponse,
    ClashCollectionResponse,
    FlexibleOperationResponse,
    GlobalOptimizationResponse,
    HealthResponse,
    OptimizerExecutionCollectionResponse,
    OptimizerExecutionDetailResponse,
    OptimizerPlanResponse,
    ReadinessResponse,
    RootResponse,
    RoomSuggestionCollectionResponse,
    StudentGroupCollectionResponse,
    StudentResolutionCollectionResponse,
    StudentRiskCollectionResponse,
    StudentScheduleChangeCollectionResponse,
    TimetableImportResponse,
)
from backend.room_resolver import (
    get_known_rooms,
    room_is_available,
    room_is_compatible,
    suggest_room_fixes_for_clash,
)
from backend.schemas import (
    RoomChangeRequest,
    TimetableEntryCreate,
    TimetableEntryResponse,
    TimetableTimeChangeRequest,
    TimetableTimeChangeResponse,
)
from backend.schedule_matching import timetable_sort_key
from backend.student_conflict_analyzer import (
    analyze_student_conflicts,
    summarize_student_conflicts,
)
from backend.student_conflict_groups import (
    build_student_conflict_groups,
    summarize_student_conflict_groups,
)
from backend.student_conflict_resolver import (
    resolve_all_student_conflict_groups,
)
from backend.student_resolution_applier import (
    StudentScheduleChange,
    apply_student_resolution,
    redo_student_resolution,
    undo_student_resolution,
)
from backend.timetable_time_service import (
    apply_manual_time_change,
    redo_manual_time_change,
    undo_manual_time_change,
)
from backend.term_service import (
    get_active_term,
    get_term,
    resolve_term_for_write,
)


# ---------------------------------------------------------------------------
# DATABASE TABLES
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# APP
# ---------------------------------------------------------------------------

configure_logging()
logger = get_logger(__name__)

runtime_configuration = validate_runtime_config()
documentation_settings = api_documentation_settings()

app = FastAPI(
    **documentation_settings,

    title="UniTime AI API",
    version="0.9.0",
)

app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=ALLOWED_HOSTS,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_api_middleware(app)
register_api_error_handlers(app)
app.include_router(auth_router)
app.include_router(enrollment_router)
app.include_router(student_router)
app.include_router(student_clash_report_router)
app.include_router(clash_report_review_router)
app.include_router(faculty_router)
app.include_router(faculty_directory_router)
app.include_router(faculty_management_router)
app.include_router(notification_router)
app.include_router(notification_job_router)
app.include_router(account_router)
app.include_router(admin_router)
app.include_router(student_identity_account_router)
app.include_router(student_identity_management_router)
app.include_router(dashboard_router)
app.include_router(academic_term_router)


# ---------------------------------------------------------------------------
# DATABASE HELPERS
# ---------------------------------------------------------------------------


def get_all_entries(
    db: Session,
    term_id: int | None = None,
) -> list[TimetableEntry]:
    selected_term_id = term_id or get_active_term(db).id
    statement = (
        select(TimetableEntry)
        .where(TimetableEntry.term_id == selected_term_id)
        .order_by(TimetableEntry.id)
    )

    return list(
        db.scalars(statement).all()
    )


def get_room_clashes(
    entries: list[TimetableEntry],
) -> list[dict]:
    return [
        clash
        for clash in detect_clashes(entries)
        if clash.get("type") == "room"
    ]


def create_change_record(
    db: Session,
    *,
    entry_id: int,
    change_type: str,
    old_room: str | None,
    new_room: str | None,
    reason: str | None = None,
    score: float | None = None,
) -> TimetableChange:
    entry = db.get(TimetableEntry, entry_id)
    change = TimetableChange(
        term_id=entry.term_id if entry is not None else get_active_term(db).id,
        entry_id=entry_id,
        change_type=change_type,
        old_room=old_room,
        new_room=new_room,
        reason=reason,
        score=score,
    )

    db.add(change)
    db.flush()

    if entry is not None:
        add_schedule_change_notifications(
            db,
            entry=entry,
            notification_type="room_change",
            title=f"Room changed for {entry.course_code or entry.course_name}",
            message=f"Room changed from {old_room or 'unassigned'} to {new_room or 'unassigned'}.",
            event_key=f"room-change:{change.id}",
            change_details={"old_room": old_room, "new_room": new_room},
        )

    return change


# ---------------------------------------------------------------------------
# BASIC API
# ---------------------------------------------------------------------------


@app.get("/", response_model=RootResponse)
def root():
    return {
        "app": "UniTime AI",
        "status": "running",
        "version": "0.9.0",
        "phase": "institutional_provisioning",
    }


@app.get("/health", response_model=HealthResponse)
def health_check():
    return {
        "status": "healthy",
        "database": "connected",
    }


# ---------------------------------------------------------------------------
# TIMETABLE CRUD
# ---------------------------------------------------------------------------


@app.post(
    "/timetable",
    response_model=TimetableEntryResponse,
    status_code=201,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def create_timetable_entry(
    entry: TimetableEntryCreate,
    term_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    acquire_timetable_write_lock(db)
    term = resolve_term_for_write(db, term_id, allow_planning=True)
    duplicate_statement = (
        select(TimetableEntry)
        .where(
            TimetableEntry.term_id == term.id,
            TimetableEntry.entry_kind == entry.entry_kind,
            TimetableEntry.course_code == entry.course_code,
            TimetableEntry.course_name == entry.course_name,
            TimetableEntry.semester == entry.semester,
            TimetableEntry.section == entry.section,
            TimetableEntry.faculty == entry.faculty,
            TimetableEntry.room == entry.room,
            TimetableEntry.day == entry.day,
            TimetableEntry.start_time == entry.start_time,
            TimetableEntry.end_time == entry.end_time,
            TimetableEntry.class_type == entry.class_type,
            TimetableEntry.raw_text == entry.raw_text,
            TimetableEntry.source == entry.source,
        )
    )

    duplicate = db.scalar(
        duplicate_statement
    )

    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail="This timetable entry already exists.",
        )

    db_entry = TimetableEntry(
        term_id=term.id,
        **entry.model_dump()
    )

    db.add(db_entry)
    db.commit()
    db.refresh(db_entry)

    return db_entry


@app.get(
    "/timetable",
    response_model=list[TimetableEntryResponse],
    dependencies=[Depends(require_coordinator_or_admin)],
)
def get_timetable(
    term_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    selected_term = get_active_term(db) if term_id is None else get_term(db, term_id)
    entries = list(
        db.scalars(
            select(TimetableEntry).where(TimetableEntry.term_id == selected_term.id)
        ).all()
    )
    return sorted(entries, key=timetable_sort_key)


@app.get(
    "/timetable/{entry_id}",
    response_model=TimetableEntryResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def get_timetable_entry(
    entry_id: int,
    db: Session = Depends(get_db),
):
    entry = db.get(
        TimetableEntry,
        entry_id,
    )

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="Timetable entry not found.",
        )

    return entry


@app.delete(
    "/timetable/{entry_id}",
    status_code=204,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def delete_timetable_entry(
    entry_id: int,
    db: Session = Depends(get_db),
):
    acquire_timetable_write_lock(db)
    entry = db.get(
        TimetableEntry,
        entry_id,
    )

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="Timetable entry not found.",
        )

    resolve_term_for_write(db, entry.term_id, allow_planning=True)

    add_schedule_change_notifications(
        db,
        entry=entry,
        notification_type="cancellation",
        title=f"Class cancelled: {entry.course_code or entry.course_name}",
        message=f"The {entry.day} class at {entry.start_time} has been removed.",
        event_key=f"cancellation:{entry.id}:{uuid4().hex}",
    )
    db.delete(entry)
    db.commit()


# ---------------------------------------------------------------------------
# TIMETABLE IMPORT
# ---------------------------------------------------------------------------


@app.post(
    "/timetable/import",
    response_model=TimetableImportResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
async def import_timetable(
    file: UploadFile = File(...),
    term_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    acquire_timetable_write_lock(db)
    term = resolve_term_for_write(db, term_id, allow_planning=True)
    return await import_timetable_file(
        file=file,
        db=db,
        term_id=term.id,
    )


# ---------------------------------------------------------------------------
# GENERAL CLASH DETECTION
# ---------------------------------------------------------------------------


@app.get(
    "/clashes",
    response_model=ClashCollectionResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def get_clashes(
    db: Session = Depends(get_db),
):
    entries = get_all_entries(
        db
    )

    clashes = detect_clashes(
        entries
    )

    return {
        "total": len(clashes),
        "clashes": clashes,
    }


# ---------------------------------------------------------------------------
# ROOM CLASH SUGGESTIONS
# ---------------------------------------------------------------------------


@app.get(
    "/clashes/room-suggestions",
    response_model=RoomSuggestionCollectionResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def get_room_clash_suggestions(
    db: Session = Depends(get_db),
):
    entries = get_all_entries(
        db
    )

    room_clashes = get_room_clashes(
        entries
    )

    resolutions = [
        suggest_room_fixes_for_clash(
            clash=clash,
            entries=entries,
        )
        for clash in room_clashes
    ]

    return {
        "room_clashes": len(
            room_clashes
        ),
        "resolutions": resolutions,
    }


# ---------------------------------------------------------------------------
# STUDENT / COHORT RISK ANALYSIS
# ---------------------------------------------------------------------------


@app.get(
    "/clashes/student-risk",
    response_model=StudentRiskCollectionResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def get_student_conflict_risks(
    db: Session = Depends(get_db),
):
    entries = get_all_entries(
        db
    )

    conflicts = analyze_student_conflicts(
        entries
    )

    summary = summarize_student_conflicts(
        conflicts
    )

    return {
        "summary": summary,
        "risks": conflicts,
    }


# ---------------------------------------------------------------------------
# STUDENT CONFLICT GROUPS
# ---------------------------------------------------------------------------


@app.get(
    "/clashes/student-groups",
    response_model=StudentGroupCollectionResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def get_student_conflict_groups(
    db: Session = Depends(get_db),
):
    entries = get_all_entries(
        db
    )

    risks = analyze_student_conflicts(
        entries
    )

    groups = build_student_conflict_groups(
        risks
    )

    summary = summarize_student_conflict_groups(
        groups
    )

    return {
        "summary": summary,
        "groups": groups,
    }


# ---------------------------------------------------------------------------
# STUDENT CONFLICT RESOLUTION SUGGESTIONS
# ---------------------------------------------------------------------------


@app.get(
    "/clashes/student-resolutions",
    response_model=StudentResolutionCollectionResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def get_student_conflict_resolutions(
    db: Session = Depends(get_db),
):
    entries = get_all_entries(
        db
    )

    risks = analyze_student_conflicts(
        entries
    )

    groups = build_student_conflict_groups(
        risks
    )

    resolutions = (
        resolve_all_student_conflict_groups(
            groups,
            entries,
        )
    )

    groups_with_suggestion = sum(
        1
        for resolution in resolutions
        if resolution["best_fix"] is not None
    )

    groups_without_suggestion = (
        len(resolutions)
        - groups_with_suggestion
    )

    fully_feasible_best_fixes = sum(
        1
        for resolution in resolutions
        if (
            resolution["best_fix"] is not None
            and resolution["best_fix"]["room_status"]
            in {
                "available",
                "online",
            }
        )
    )

    best_fixes_requiring_room = sum(
        1
        for resolution in resolutions
        if (
            resolution["best_fix"] is not None
            and resolution["best_fix"]["room_status"]
            == "requires_assignment"
        )
    )

    return {
        "summary": {
            "total_groups": len(
                groups
            ),
            "groups_with_suggestion": (
                groups_with_suggestion
            ),
            "groups_without_suggestion": (
                groups_without_suggestion
            ),
            "fully_feasible_best_fixes": (
                fully_feasible_best_fixes
            ),
            "best_fixes_requiring_room": (
                best_fixes_requiring_room
            ),
            "important_note": (
                "Student/cohort conflicts are inferred from "
                "timetable structure without individual "
                "enrollment data. These resolutions are "
                "planning suggestions only."
            ),
        },
        "resolutions": resolutions,
    }


# ---------------------------------------------------------------------------
# PHASE 2 - GLOBAL TIMETABLE OPTIMIZER
# ---------------------------------------------------------------------------


@app.get(
    "/optimizer/global",
    response_model=GlobalOptimizationResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def get_global_timetable_optimization(
    limit: int = 20,
    db: Session = Depends(get_db),
):
    """
    Rank globally beneficial timetable moves.

    READ-ONLY:
    This endpoint never modifies the database.

    The optimizer evaluates candidate student/cohort conflict
    resolutions against the entire timetable and rejects moves
    that worsen general clashes or global student/cohort risk.
    """

    if limit < 1:
        raise HTTPException(
            status_code=422,
            detail=(
                "limit must be greater than or equal to 1."
            ),
        )

    if limit > 100:
        raise HTTPException(
            status_code=422,
            detail=(
                "limit must be less than or equal to 100."
            ),
        )

    entries = get_all_entries(
        db
    )

    result = optimize_timetable_globally(
        entries,
        limit=limit,
    )

    return result


# ---------------------------------------------------------------------------
# PHASE 2 - MULTI-STEP OPTIMIZATION PLAN
# ---------------------------------------------------------------------------


@app.get(
    "/optimizer/plan",
    response_model=OptimizerPlanResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def get_multi_step_optimization_plan(
    max_steps: int = 5,
    db: Session = Depends(get_db),
):
    try:
        entries = get_all_entries(db)
        return build_multi_step_optimization_plan(
            entries,
            max_steps=max_steps,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# PHASE 2 - APPLY MULTI-STEP OPTIMIZATION
# ---------------------------------------------------------------------------


@app.post(
    "/optimizer/plan/apply",
    response_model=FlexibleOperationResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def apply_multi_step_optimizer_plan(
    max_steps: int = 5,
    db: Session = Depends(get_db),
):
    acquire_timetable_write_lock(db)
    try:
        return apply_multi_step_plan_with_history(
            db,
            max_steps=max_steps,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# APPLY GLOBAL OPTIMIZER BEST MOVE
# ---------------------------------------------------------------------------


@app.post(
    "/optimizer/global/apply-best",
    response_model=FlexibleOperationResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def apply_global_optimizer_best_move(
    db: Session = Depends(get_db),
):
    acquire_timetable_write_lock(db)
    try:
        return apply_global_best_move(db)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# APPLY STUDENT CONFLICT BEST FIX
# ---------------------------------------------------------------------------


@app.post(
    "/clashes/student-groups/{group_id}/apply-best-fix",
    response_model=FlexibleOperationResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def apply_student_conflict_best_fix(
    group_id: int,
    db: Session = Depends(get_db),
):
    acquire_timetable_write_lock(db)
    try:
        return apply_student_resolution(
            db,
            group_id=group_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# STUDENT SCHEDULE CHANGE HISTORY
# ---------------------------------------------------------------------------


@app.get(
    "/student-schedule-changes",
    response_model=StudentScheduleChangeCollectionResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def get_student_schedule_changes(
    term_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    selected_term = get_active_term(db) if term_id is None else get_term(db, term_id)
    statement = (
        select(StudentScheduleChange)
        .where(StudentScheduleChange.term_id == selected_term.id)
        .order_by(
            StudentScheduleChange.id.desc()
        )
    )

    changes = list(
        db.scalars(statement).all()
    )

    return {
        "total": len(changes),
        "changes": [
            {
                "id": change.id,
                "term_id": change.term_id,
                "entry_id": change.entry_id,
                "group_id": change.group_id,
                "change_type": (
                    change.change_type
                ),
                "old_day": change.old_day,
                "old_start_time": (
                    change.old_start_time
                ),
                "old_end_time": (
                    change.old_end_time
                ),
                "new_day": change.new_day,
                "new_start_time": (
                    change.new_start_time
                ),
                "new_end_time": (
                    change.new_end_time
                ),
                "score": change.score,
                "risk_cost_before": (
                    change.risk_cost_before
                ),
                "risk_cost_after": (
                    change.risk_cost_after
                ),
                "total_risks_before": (
                    change.total_risks_before
                ),
                "total_risks_after": (
                    change.total_risks_after
                ),
                "undone": change.undone,
                "created_at": (
                    change.created_at.isoformat()
                    if change.created_at
                    else None
                ),
            }
            for change in changes
        ],
    }


# ---------------------------------------------------------------------------
# UNDO STUDENT SCHEDULE CHANGE
# ---------------------------------------------------------------------------


@app.post(
    "/student-schedule-changes/{change_id}/undo",
    response_model=FlexibleOperationResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def undo_student_schedule_change(
    change_id: int,
    db: Session = Depends(get_db),
):
    acquire_timetable_write_lock(db)
    try:
        return undo_student_resolution(
            db,
            change_id=change_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# REDO STUDENT SCHEDULE CHANGE
# ---------------------------------------------------------------------------


@app.post(
    "/student-schedule-changes/{change_id}/redo",
    response_model=FlexibleOperationResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def redo_student_schedule_change(
    change_id: int,
    db: Session = Depends(get_db),
):
    acquire_timetable_write_lock(db)
    try:
        return redo_student_resolution(
            db,
            change_id=change_id,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


# ---------------------------------------------------------------------------
# MANUAL SAFE ROOM CHANGE
# ---------------------------------------------------------------------------


@app.patch(
    "/timetable/{entry_id}/room",
    response_model=TimetableEntryResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def change_timetable_room(
    entry_id: int,
    request: RoomChangeRequest,
    db: Session = Depends(get_db),
):
    acquire_timetable_write_lock(db)
    entry = db.get(
        TimetableEntry,
        entry_id,
    )

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail="Timetable entry not found.",
        )

    resolve_term_for_write(db, entry.term_id, allow_planning=True)

    requested_room = normalize_room(
        request.room
    )

    entries = get_all_entries(
        db,
        term_id=entry.term_id,
    )

    known_rooms = get_known_rooms(
        entries
    )

    normalized_known_rooms = {
        normalize_room(room)
        for room in known_rooms
    }

    if requested_room not in normalized_known_rooms:
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "Requested room does not exist "
                    "in the known timetable room list."
                ),
                "requested_room": requested_room,
                "known_rooms": known_rooms,
            },
        )

    current_room = (
        normalize_room(entry.room)
        if entry.room
        else None
    )

    if requested_room == current_room:
        raise HTTPException(
            status_code=400,
            detail=(
                "Requested room is already assigned "
                "to this timetable entry."
            ),
        )

    if not room_is_compatible(
        requested_room,
        entry.class_type,
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "message": (
                    "Requested room is not compatible "
                    "with this class type."
                ),
                "class_type": entry.class_type,
                "requested_room": requested_room,
            },
        )

    if not room_is_available(
        room=requested_room,
        day=entry.day,
        start_time=entry.start_time,
        end_time=entry.end_time,
        entries=entries,
        ignore_entry_id=entry.id,
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Requested room is already occupied "
                    "during this timetable entry."
                ),
                "requested_room": requested_room,
                "day": entry.day,
                "start_time": entry.start_time,
                "end_time": entry.end_time,
            },
        )

    old_room = entry.room

    entry.room = requested_room

    db.flush()

    refreshed_entries = get_all_entries(
        db,
        term_id=entry.term_id,
    )

    new_room_clashes = [
        clash
        for clash in get_room_clashes(
            refreshed_entries
        )
        if (
            clash["entry_1"]["id"] == entry.id
            or clash["entry_2"]["id"] == entry.id
        )
    ]

    if new_room_clashes:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Room change was rejected because "
                    "it would create another room clash."
                ),
                "clashes": new_room_clashes,
            },
        )

    create_change_record(
        db,
        entry_id=entry.id,
        change_type="manual_room_change",
        old_room=old_room,
        new_room=requested_room,
        reason="Manual room change",
        score=None,
    )

    try:
        db.commit()

    except Exception:
        db.rollback()
        raise

    db.refresh(entry)

    return entry


@app.patch(
    "/timetable/{entry_id}/time",
    response_model=TimetableTimeChangeResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def change_timetable_time(
    entry_id: int,
    request: TimetableTimeChangeRequest,
    db: Session = Depends(get_db),
):
    acquire_timetable_write_lock(db)
    return apply_manual_time_change(
        db,
        entry_id=entry_id,
        request=request,
    )


# ---------------------------------------------------------------------------
# APPLY BEST ROOM FIX
# ---------------------------------------------------------------------------


@app.post(
    "/clashes/room/{entry_1_id}/{entry_2_id}/apply-best-fix",
    response_model=FlexibleOperationResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def apply_best_room_fix(
    entry_1_id: int,
    entry_2_id: int,
    db: Session = Depends(get_db),
):
    acquire_timetable_write_lock(db)
    entries = get_all_entries(
        db
    )

    room_clashes_before = get_room_clashes(
        entries
    )

    before_count = len(
        room_clashes_before
    )

    requested_pair = {
        entry_1_id,
        entry_2_id,
    }

    target_clash = None

    for clash in room_clashes_before:
        clash_pair = {
            clash["entry_1"]["id"],
            clash["entry_2"]["id"],
        }

        if clash_pair == requested_pair:
            target_clash = clash
            break

    if target_clash is None:
        raise HTTPException(
            status_code=404,
            detail={
                "message": (
                    "The specified timetable entries "
                    "do not currently form a room clash."
                ),
                "entry_1_id": entry_1_id,
                "entry_2_id": entry_2_id,
            },
        )

    resolution = suggest_room_fixes_for_clash(
        clash=target_clash,
        entries=entries,
    )

    best_fix = resolution.get(
        "best_fix"
    )

    if best_fix is None:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "No safe room alternative is "
                    "currently available for this clash."
                ),
                "clash": target_clash,
            },
        )

    target_entry = db.get(
        TimetableEntry,
        best_fix["entry_id"],
    )

    if target_entry is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Best-fix timetable entry "
                "no longer exists."
            ),
        )

    old_room = target_entry.room

    new_room = normalize_room(
        best_fix["to_room"]
    )

    if not room_is_compatible(
        new_room,
        target_entry.class_type,
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Best-fix room is no longer "
                    "compatible with the timetable entry."
                ),
                "room": new_room,
                "class_type": target_entry.class_type,
            },
        )

    current_entries = get_all_entries(
        db
    )

    if not room_is_available(
        room=new_room,
        day=target_entry.day,
        start_time=target_entry.start_time,
        end_time=target_entry.end_time,
        entries=current_entries,
        ignore_entry_id=target_entry.id,
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "The recommended room became "
                    "occupied before the fix "
                    "could be applied."
                ),
                "room": new_room,
                "entry_id": target_entry.id,
            },
        )

    target_entry.room = new_room

    db.flush()

    updated_entries = get_all_entries(
        db
    )

    room_clashes_after = get_room_clashes(
        updated_entries
    )

    after_count = len(
        room_clashes_after
    )

    target_new_clashes = [
        clash
        for clash in room_clashes_after
        if (
            clash["entry_1"]["id"] == target_entry.id
            or clash["entry_2"]["id"] == target_entry.id
        )
    ]

    if target_new_clashes:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Best fix was rejected because "
                    "it created another room clash."
                ),
                "clashes": target_new_clashes,
            },
        )

    if after_count >= before_count:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Best fix was rejected because "
                    "it did not reduce the room-clash count."
                ),
                "before": before_count,
                "after": after_count,
            },
        )

    change = create_change_record(
        db,
        entry_id=target_entry.id,
        change_type="auto_room_fix",
        old_room=old_room,
        new_room=new_room,
        reason=target_clash.get(
            "reason"
        ),
        score=float(
            best_fix["score"]
        ),
    )

    try:
        db.commit()

    except Exception:
        db.rollback()
        raise

    db.refresh(target_entry)
    db.refresh(change)

    return {
        "success": True,
        "message": (
            "Best room fix applied successfully."
        ),
        "change_id": change.id,
        "applied_fix": {
            "entry_id": target_entry.id,
            "course_code": (
                target_entry.course_code
            ),
            "course_name": (
                target_entry.course_name
            ),
            "day": target_entry.day,
            "start_time": (
                target_entry.start_time
            ),
            "end_time": (
                target_entry.end_time
            ),
            "from_room": old_room,
            "to_room": target_entry.room,
            "score": best_fix["score"],
            "reasons": best_fix["reasons"],
        },
        "room_clashes_before": before_count,
        "room_clashes_after": after_count,
        "remaining_room_clashes": (
            room_clashes_after
        ),
    }


# ---------------------------------------------------------------------------
# ROOM CHANGE HISTORY
# ---------------------------------------------------------------------------


@app.get(
    "/changes",
    response_model=ChangeCollectionResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def get_changes(
    term_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    selected_term = get_active_term(db) if term_id is None else get_term(db, term_id)
    statement = (
        select(TimetableChange)
        .where(TimetableChange.term_id == selected_term.id)
        .order_by(
            TimetableChange.id.desc()
        )
    )

    changes = list(
        db.scalars(statement).all()
    )

    return {
        "total": len(changes),
        "changes": [
            {
                "id": change.id,
                "term_id": change.term_id,
                "entry_id": change.entry_id,
                "change_type": change.change_type,
                "old_room": change.old_room,
                "new_room": change.new_room,
                "old_day": change.old_day,
                "new_day": change.new_day,
                "old_start_time": change.old_start_time,
                "new_start_time": change.new_start_time,
                "old_end_time": change.old_end_time,
                "new_end_time": change.new_end_time,
                "reason": change.reason,
                "score": change.score,
                "created_at": (
                    change.created_at.isoformat()
                    if change.created_at
                    else None
                ),
                "undone": change.undone,
            }
            for change in changes
        ],
    }


# ---------------------------------------------------------------------------
# UNDO ROOM CHANGE
# ---------------------------------------------------------------------------


@app.post(
    "/changes/{change_id}/undo",
    response_model=FlexibleOperationResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def undo_change(
    change_id: int,
    db: Session = Depends(get_db),
):
    acquire_timetable_write_lock(db)
    change = db.get(
        TimetableChange,
        change_id,
    )

    if change is None:
        raise HTTPException(
            status_code=404,
            detail="Change record not found.",
        )

    resolve_term_for_write(db, change.term_id, allow_planning=True)

    if change.change_type == "manual_time_change":
        return undo_manual_time_change(db, change_id=change.id)

    if change.undone:
        raise HTTPException(
            status_code=409,
            detail=(
                "This change has already been undone."
            ),
        )

    entry = db.get(
        TimetableEntry,
        change.entry_id,
    )

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "The timetable entry associated "
                "with this change no longer exists."
            ),
        )

    current_normalized_room = (
        normalize_room(entry.room)
        if entry.room
        else None
    )

    expected_normalized_room = (
        normalize_room(change.new_room)
        if change.new_room
        else None
    )

    if current_normalized_room != expected_normalized_room:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Undo rejected because the "
                    "timetable entry has changed "
                    "since this history record "
                    "was created."
                ),
                "current_room": entry.room,
                "expected_room": change.new_room,
            },
        )

    room_clashes_before = get_room_clashes(
        get_all_entries(db, term_id=change.term_id)
    )

    before_count = len(
        room_clashes_before
    )

    current_room = entry.room

    entry.room = change.old_room

    db.flush()

    entries_after_undo = get_all_entries(
        db,
        term_id=change.term_id,
    )

    room_clashes_after = get_room_clashes(
        entries_after_undo
    )

    after_count = len(
        room_clashes_after
    )

    reintroduced_clashes = [
        clash
        for clash in room_clashes_after
        if (
            clash["entry_1"]["id"] == entry.id
            or clash["entry_2"]["id"] == entry.id
        )
    ]

    change.undone = True

    add_schedule_change_notifications(
        db,
        entry=entry,
        notification_type="room_change",
        title=f"Room change reversed for {entry.course_code or entry.course_name}",
        message=f"Room restored from {current_room or 'unassigned'} to {entry.room or 'unassigned'}.",
        event_key=f"room-change-undo:{change.id}",
        change_details={"old_room": current_room, "new_room": entry.room},
    )

    try:
        db.commit()

    except Exception:
        db.rollback()
        raise

    db.refresh(entry)
    db.refresh(change)

    return {
        "success": True,
        "message": (
            "Change undone successfully."
        ),
        "change_id": change.id,
        "entry_id": entry.id,
        "from_room": current_room,
        "restored_room": entry.room,
        "undone": change.undone,
        "room_clashes_before": before_count,
        "room_clashes_after": after_count,
        "reintroduced_room_clashes": len(
            reintroduced_clashes
        ),
        "warnings": (
            [
                (
                    "Undo restored the previous "
                    "timetable state but "
                    "reintroduced room clash(es)."
                )
            ]
            if reintroduced_clashes
            else []
        ),
        "reintroduced_clashes": (
            reintroduced_clashes
        ),
    }


# ---------------------------------------------------------------------------
# REDO ROOM CHANGE
# ---------------------------------------------------------------------------


@app.post(
    "/changes/{change_id}/redo",
    response_model=FlexibleOperationResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def redo_change(
    change_id: int,
    db: Session = Depends(get_db),
):
    acquire_timetable_write_lock(db)
    change = db.get(
        TimetableChange,
        change_id,
    )

    if change is None:
        raise HTTPException(
            status_code=404,
            detail="Change record not found.",
        )

    resolve_term_for_write(db, change.term_id, allow_planning=True)

    if change.change_type == "manual_time_change":
        return redo_manual_time_change(db, change_id=change.id)

    if not change.undone:
        raise HTTPException(
            status_code=409,
            detail=(
                "This change is currently active "
                "and does not need to be redone."
            ),
        )

    entry = db.get(
        TimetableEntry,
        change.entry_id,
    )

    if entry is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "The timetable entry associated "
                "with this change no longer exists."
            ),
        )

    current_normalized_room = (
        normalize_room(entry.room)
        if entry.room
        else None
    )

    expected_old_room = (
        normalize_room(change.old_room)
        if change.old_room
        else None
    )

    if current_normalized_room != expected_old_room:
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Redo rejected because the "
                    "timetable entry has changed "
                    "since it was undone."
                ),
                "current_room": entry.room,
                "expected_room": change.old_room,
            },
        )

    if change.new_room is None:
        raise HTTPException(
            status_code=409,
            detail=(
                "Redo rejected because this "
                "room change has no target room."
            ),
        )

    target_room = normalize_room(
        change.new_room
    )

    entries_before = get_all_entries(
        db,
        term_id=change.term_id,
    )

    before_count = len(
        get_room_clashes(
            entries_before
        )
    )

    if not room_is_compatible(
        target_room,
        entry.class_type,
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Redo rejected because the "
                    "target room is no longer "
                    "compatible with the class."
                ),
                "room": target_room,
                "class_type": entry.class_type,
            },
        )

    if not room_is_available(
        room=target_room,
        day=entry.day,
        start_time=entry.start_time,
        end_time=entry.end_time,
        entries=entries_before,
        ignore_entry_id=entry.id,
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Redo rejected because the "
                    "target room is currently occupied."
                ),
                "room": target_room,
                "day": entry.day,
                "start_time": entry.start_time,
                "end_time": entry.end_time,
            },
        )

    old_current_room = entry.room

    entry.room = target_room

    db.flush()

    entries_after = get_all_entries(
        db,
        term_id=change.term_id,
    )

    room_clashes_after = get_room_clashes(
        entries_after
    )

    after_count = len(
        room_clashes_after
    )

    new_entry_clashes = [
        clash
        for clash in room_clashes_after
        if (
            clash["entry_1"]["id"] == entry.id
            or clash["entry_2"]["id"] == entry.id
        )
    ]

    if new_entry_clashes:
        db.rollback()

        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    "Redo rejected because "
                    "reapplying the change would "
                    "create a room clash."
                ),
                "clashes": new_entry_clashes,
            },
        )

    change.undone = False

    add_schedule_change_notifications(
        db,
        entry=entry,
        notification_type="room_change",
        title=f"Room change reapplied for {entry.course_code or entry.course_name}",
        message=f"Room changed from {old_current_room or 'unassigned'} to {entry.room or 'unassigned'}.",
        event_key=f"room-change-redo:{change.id}",
        change_details={"old_room": old_current_room, "new_room": entry.room},
    )

    try:
        db.commit()

    except Exception:
        db.rollback()
        raise

    db.refresh(entry)
    db.refresh(change)

    return {
        "success": True,
        "message": (
            "Change reapplied successfully."
        ),
        "change_id": change.id,
        "entry_id": entry.id,
        "from_room": old_current_room,
        "reapplied_room": entry.room,
        "undone": change.undone,
        "room_clashes_before": before_count,
        "room_clashes_after": after_count,
    }


# ---------------------------------------------------------------------------
# UNIFIED AUDIT TRAIL
# ---------------------------------------------------------------------------


@app.get(
    "/audit-trail",
    response_model=AuditTrailResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def get_audit_trail(
    term_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    selected_term = get_active_term(db) if term_id is None else get_term(db, term_id)
    room_statement = (
        select(TimetableChange)
        .where(TimetableChange.term_id == selected_term.id)
        .order_by(TimetableChange.id)
    )

    student_statement = (
        select(StudentScheduleChange)
        .where(StudentScheduleChange.term_id == selected_term.id)
        .order_by(StudentScheduleChange.id)
    )

    room_changes = list(
        db.scalars(room_statement).all()
    )

    student_changes = list(
        db.scalars(student_statement).all()
    )

    audit_items: list[dict] = []

    for change in room_changes:
        entry = db.get(
            TimetableEntry,
            change.entry_id,
        )

        audit_items.append(
            {
                "audit_type": (
                    "timetable_time_change"
                    if change.change_type == "manual_time_change"
                    else "room_change"
                ),
                "term_id": change.term_id,
                "history_id": change.id,
                "entry_id": change.entry_id,
                "course_code": (
                    entry.course_code
                    if entry
                    else None
                ),
                "course_name": (
                    entry.course_name
                    if entry
                    else None
                ),
                "change_type": (
                    change.change_type
                ),
                "before": {
                    "room": change.old_room,
                    "day": change.old_day,
                    "start_time": change.old_start_time,
                    "end_time": change.old_end_time,
                },
                "after": {
                    "room": change.new_room,
                    "day": change.new_day,
                    "start_time": change.new_start_time,
                    "end_time": change.new_end_time,
                },
                "reason": (
                    change.reason
                ),
                "score": (
                    change.score
                ),
                "undone": (
                    change.undone
                ),
                "created_at": (
                    change.created_at.isoformat()
                    if change.created_at
                    else None
                ),
            }
        )

    for change in student_changes:
        entry = db.get(
            TimetableEntry,
            change.entry_id,
        )

        audit_items.append(
            {
                "audit_type": (
                    "student_schedule_change"
                ),
                "term_id": change.term_id,
                "history_id": (
                    change.id
                ),
                "entry_id": (
                    change.entry_id
                ),
                "course_code": (
                    entry.course_code
                    if entry
                    else None
                ),
                "course_name": (
                    entry.course_name
                    if entry
                    else None
                ),
                "group_id": (
                    change.group_id
                ),
                "change_type": (
                    change.change_type
                ),
                "before": {
                    "day": (
                        change.old_day
                    ),
                    "start_time": (
                        change.old_start_time
                    ),
                    "end_time": (
                        change.old_end_time
                    ),
                },
                "after": {
                    "day": (
                        change.new_day
                    ),
                    "start_time": (
                        change.new_start_time
                    ),
                    "end_time": (
                        change.new_end_time
                    ),
                },
                "risk_cost_before": (
                    change.risk_cost_before
                ),
                "risk_cost_after": (
                    change.risk_cost_after
                ),
                "score": (
                    change.score
                ),
                "undone": (
                    change.undone
                ),
                "created_at": (
                    change.created_at.isoformat()
                    if change.created_at
                    else None
                ),
            }
        )

    audit_items.sort(
        key=lambda item: (
            item["created_at"] is not None,
            item["created_at"] or "",
        ),
        reverse=True,
    )

    active_count = sum(
        1
        for item in audit_items
        if not item["undone"]
    )

    undone_count = (
        len(audit_items)
        - active_count
    )

    room_count = sum(
        1
        for item in audit_items
        if item["audit_type"]
        == "room_change"
    )

    time_count = sum(
        1
        for item in audit_items
        if item["audit_type"]
        == "timetable_time_change"
    )

    student_count = sum(
        1
        for item in audit_items
        if item["audit_type"]
        == "student_schedule_change"
    )

    return {
        "summary": {
            "total_changes": len(
                audit_items
            ),
            "active_changes": (
                active_count
            ),
            "undone_changes": (
                undone_count
            ),
            "room_changes": (
                room_count
            ),
            "timetable_time_changes": (
                time_count
            ),
            "student_schedule_changes": (
                student_count
            ),
        },
        "audit_trail": (
            audit_items
        ),
    }

@app.post(
    "/optimizer/executions/{execution_id}/undo",
    response_model=FlexibleOperationResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def undo_optimizer_execution_endpoint(
    execution_id: str,
    db: Session = Depends(get_db),
):
    acquire_timetable_write_lock(db)
    try:
        return undo_optimizer_execution(
            db,
            execution_id=execution_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@app.post(
    "/optimizer/executions/{execution_id}/redo",
    response_model=FlexibleOperationResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def redo_optimizer_execution_endpoint(
    execution_id: str,
    db: Session = Depends(get_db),
):
    acquire_timetable_write_lock(db)
    try:
        return redo_optimizer_execution(
            db,
            execution_id=execution_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc

@app.get(
    "/optimizer/executions",
    response_model=OptimizerExecutionCollectionResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def list_optimizer_executions_endpoint(
    term_id: int | None = Query(default=None, gt=0),
    db: Session = Depends(get_db),
):
    selected_term = get_active_term(db) if term_id is None else get_term(db, term_id)
    return {
        "executions": list_optimizer_executions(db, term_id=selected_term.id),
    }


@app.get(
    "/optimizer/executions/{execution_id}",
    response_model=OptimizerExecutionDetailResponse,
    dependencies=[Depends(require_coordinator_or_admin)],
)
def get_optimizer_execution_endpoint(
    execution_id: str,
    db: Session = Depends(get_db),
):
    try:
        return get_optimizer_execution_detail(
            db,
            execution_id=execution_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        ) from exc

@app.get("/ready", response_model=ReadinessResponse)
def readiness_endpoint():
    try:
        return check_readiness(require_migration_head=True)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

