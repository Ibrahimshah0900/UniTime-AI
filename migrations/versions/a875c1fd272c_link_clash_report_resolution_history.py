"""link clash report resolution history

Revision ID: a875c1fd272c
Revises: 36bb9325c02a
Create Date: 2026-08-25 06:24:07.304418

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a875c1fd272c'
down_revision: Union[str, Sequence[str], None] = '36bb9325c02a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("student_schedule_changes") as batch_op:
        batch_op.add_column(sa.Column("report_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("actor_user_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("candidate_id", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("safety_status", sa.String(length=30), nullable=True))
        batch_op.add_column(sa.Column("report_resolution_note", sa.Text(), nullable=True))
        batch_op.alter_column(
            "group_id",
            existing_type=sa.Integer(),
            nullable=True,
        )
        batch_op.create_index(
            "ix_student_schedule_changes_actor_user_id",
            ["actor_user_id"],
            unique=False,
        )
        batch_op.create_index(
            "ix_student_schedule_changes_report_id",
            ["report_id"],
            unique=False,
        )
        batch_op.create_foreign_key(
            "fk_student_schedule_changes_report_id_student_clash_reports",
            "student_clash_reports",
            ["report_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_foreign_key(
            "fk_student_schedule_changes_actor_user_id_users",
            "users",
            ["actor_user_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_check_constraint(
            "ck_student_schedule_changes_safety_status",
            "safety_status IS NULL OR safety_status IN "
            "('SAFE','CONDITIONALLY_SAFE','INSUFFICIENT_DATA','REJECTED')",
        )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        sa.text(
            "UPDATE student_schedule_changes "
            "SET group_id = COALESCE(group_id, report_id, 0) "
            "WHERE group_id IS NULL"
        )
    )
    with op.batch_alter_table("student_schedule_changes") as batch_op:
        batch_op.drop_constraint(
            "ck_student_schedule_changes_safety_status",
            type_="check",
        )
        batch_op.drop_constraint(
            "fk_student_schedule_changes_actor_user_id_users",
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            "fk_student_schedule_changes_report_id_student_clash_reports",
            type_="foreignkey",
        )
        batch_op.drop_index("ix_student_schedule_changes_report_id")
        batch_op.drop_index("ix_student_schedule_changes_actor_user_id")
        batch_op.alter_column(
            "group_id",
            existing_type=sa.Integer(),
            nullable=False,
        )
        batch_op.drop_column("report_resolution_note")
        batch_op.drop_column("safety_status")
        batch_op.drop_column("candidate_id")
        batch_op.drop_column("actor_user_id")
        batch_op.drop_column("report_id")
