"""add academic term lifecycle

Revision ID: 8ff39f7b22e6
Revises: ee8c90bdac09
Create Date: 2026-08-25 04:50:21.072799

"""
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8ff39f7b22e6'
down_revision: Union[str, Sequence[str], None] = 'ee8c90bdac09'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TERM_TABLES = (
    "faculty_class_assignments",
    "notifications",
    "optimizer_executions",
    "student_clash_reports",
    "student_enrollments",
    "student_schedule_changes",
    "timetable_changes",
    "timetable_entries",
)


def _add_backfilled_term_column(table_name: str) -> None:
    foreign_key_name = f"fk_{table_name}_term_id_academic_terms"
    index_name = f"ix_{table_name}_term_id"
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.add_column(sa.Column("term_id", sa.Integer(), nullable=True))
        batch_op.create_index(index_name, ["term_id"], unique=False)
        batch_op.create_foreign_key(
            foreign_key_name,
            "academic_terms",
            ["term_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    table = sa.table(table_name, sa.column("term_id", sa.Integer()))
    op.execute(table.update().values(term_id=1))


def _make_term_column_required(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.alter_column(
            "term_id",
            existing_type=sa.Integer(),
            nullable=False,
        )


def _drop_term_column(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch_op:
        batch_op.drop_constraint(
            f"fk_{table_name}_term_id_academic_terms",
            type_="foreignkey",
        )
        batch_op.drop_index(f"ix_{table_name}_term_id")
        batch_op.drop_column("term_id")


def upgrade() -> None:
    """Create academic terms and attach all existing records to a legacy term."""
    op.create_table('academic_terms',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('name', sa.String(length=120), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('starts_on', sa.Date(), nullable=True),
    sa.Column('ends_on', sa.Date(), nullable=True),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('activated_at', sa.DateTime(), nullable=True),
    sa.Column('archived_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("status IN ('planning','active','archived')", name='ck_academic_terms_status'),
    sa.CheckConstraint('starts_on IS NULL OR ends_on IS NULL OR starts_on <= ends_on', name='ck_academic_terms_date_order'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('code')
    )
    op.create_index(op.f('ix_academic_terms_status'), 'academic_terms', ['status'], unique=False)
    op.create_index('uq_academic_terms_single_active', 'academic_terms', ['status'], unique=True, sqlite_where=sa.text("status = 'active'"), postgresql_where=sa.text("status = 'active'"))
    now = datetime.now(UTC).replace(tzinfo=None)
    academic_terms = sa.table(
        "academic_terms",
        sa.column("id", sa.Integer()),
        sa.column("code", sa.String()),
        sa.column("name", sa.String()),
        sa.column("status", sa.String()),
        sa.column("activated_at", sa.DateTime()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    op.bulk_insert(
        academic_terms,
        [
            {
                "id": 1,
                "code": "LEGACY-IMPORTED",
                "name": "Legacy Imported Term",
                "status": "active",
                "activated_at": now,
                "created_at": now,
                "updated_at": now,
            }
        ],
    )

    for table_name in TERM_TABLES:
        _add_backfilled_term_column(table_name)

    with op.batch_alter_table("faculty_class_assignments") as batch_op:
        batch_op.drop_constraint(
            "uq_faculty_class_assignment_identity",
            type_="unique",
        )
        batch_op.alter_column("term_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_unique_constraint(
            "uq_faculty_class_assignment_identity",
            ["faculty_user_id", "term_id", "course_code", "section", "semester"],
        )

    with op.batch_alter_table("student_enrollments") as batch_op:
        batch_op.drop_constraint("uq_student_enrollment_identity", type_="unique")
        batch_op.alter_column("term_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_unique_constraint(
            "uq_student_enrollment_identity",
            ["user_id", "term_id", "course_code", "section", "semester"],
        )

    for table_name in TERM_TABLES:
        if table_name not in {"faculty_class_assignments", "student_enrollments"}:
            _make_term_column_required(table_name)


def downgrade() -> None:
    """Remove term identity while restoring the previous uniqueness rules."""
    with op.batch_alter_table("student_enrollments") as batch_op:
        batch_op.drop_constraint("uq_student_enrollment_identity", type_="unique")
        batch_op.drop_constraint(
            "fk_student_enrollments_term_id_academic_terms",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_student_enrollments_term_id")
        batch_op.drop_column("term_id")
        batch_op.create_unique_constraint(
            "uq_student_enrollment_identity",
            ["user_id", "course_code", "section", "semester"],
        )

    with op.batch_alter_table("faculty_class_assignments") as batch_op:
        batch_op.drop_constraint(
            "uq_faculty_class_assignment_identity",
            type_="unique",
        )
        batch_op.drop_constraint(
            "fk_faculty_class_assignments_term_id_academic_terms",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_faculty_class_assignments_term_id")
        batch_op.drop_column("term_id")
        batch_op.create_unique_constraint(
            "uq_faculty_class_assignment_identity",
            ["faculty_user_id", "course_code", "section", "semester"],
        )

    for table_name in reversed(TERM_TABLES):
        if table_name not in {"faculty_class_assignments", "student_enrollments"}:
            _drop_term_column(table_name)

    op.drop_index('uq_academic_terms_single_active', table_name='academic_terms')
    op.drop_index(op.f('ix_academic_terms_status'), table_name='academic_terms')
    op.drop_table('academic_terms')
