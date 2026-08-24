from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class FlexibleOperationResponse(BaseModel):
    """Preserve legacy optimizer payloads while publishing an object contract."""

    model_config = ConfigDict(extra="allow")


class RootResponse(BaseModel):
    app: str
    status: str
    version: str
    phase: str


class HealthResponse(BaseModel):
    status: str
    database: str


class MigrationReadinessResponse(BaseModel):
    managed: bool
    revision: str
    expected_revision: str
    at_head: bool


class ReadinessResponse(BaseModel):
    status: str
    database: str
    migrations: MigrationReadinessResponse


class TimetableImportError(BaseModel):
    row: int
    type: str
    details: list[dict[str, Any]]


class TimetableImportResponse(BaseModel):
    filename: str
    rows_read: int
    imported: int
    duplicates: int
    invalid: int
    column_mapping: dict[str, str]
    errors: list[TimetableImportError]


class ClashCollectionResponse(BaseModel):
    total: int
    clashes: list[dict[str, Any]]


class RoomSuggestionCollectionResponse(BaseModel):
    room_clashes: int
    resolutions: list[dict[str, Any]]


class StudentRiskCollectionResponse(BaseModel):
    summary: dict[str, Any]
    risks: list[dict[str, Any]]


class StudentGroupCollectionResponse(BaseModel):
    summary: dict[str, Any]
    groups: list[dict[str, Any]]


class StudentResolutionCollectionResponse(BaseModel):
    summary: dict[str, Any]
    resolutions: list[dict[str, Any]]


class NotificationReadAllResponse(BaseModel):
    updated: int


class OptimizerExecutionCollectionResponse(BaseModel):
    executions: list[dict[str, Any]]


class ChangeCollectionResponse(BaseModel):
    total: int
    changes: list[dict[str, Any]]


class AuditTrailResponse(BaseModel):
    summary: dict[str, int]
    audit_trail: list[dict[str, Any]]
