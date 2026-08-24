from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    STUDENT = "student"
    FACULTY = "faculty"
    COORDINATOR = "coordinator"
    ADMIN = "admin"


ALL_USER_ROLES = frozenset(role.value for role in UserRole)
PRIVILEGED_USER_ROLES = frozenset(
    {
        UserRole.FACULTY.value,
        UserRole.COORDINATOR.value,
        UserRole.ADMIN.value,
    }
)
