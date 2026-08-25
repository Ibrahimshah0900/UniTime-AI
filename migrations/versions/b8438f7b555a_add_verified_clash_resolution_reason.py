"""add verified clash resolution reason

Revision ID: b8438f7b555a
Revises: 174e0a995fe0
Create Date: 2026-08-25 13:50:39.316952

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8438f7b555a'
down_revision: Union[str, Sequence[str], None] = '174e0a995fe0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("student_clash_reports") as batch_op:
        batch_op.add_column(
            sa.Column("resolution_reason", sa.String(length=40), nullable=True)
        )
        batch_op.create_check_constraint(
            "ck_student_clash_reports_resolution_reason",
            "resolution_reason IS NULL OR resolution_reason IN "
            "('timetable_changed','enrollment_corrected','course_dropped',"
            "'other_verified_correction')",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("student_clash_reports") as batch_op:
        batch_op.drop_constraint(
            "ck_student_clash_reports_resolution_reason",
            type_="check",
        )
        batch_op.drop_column("resolution_reason")
