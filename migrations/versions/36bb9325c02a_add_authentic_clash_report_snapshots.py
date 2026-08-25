"""add authentic clash report snapshots

Revision ID: 36bb9325c02a
Revises: 5989aedcfe45
Create Date: 2026-08-25 05:45:05.337150

"""
import hashlib
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '36bb9325c02a'
down_revision: Union[str, Sequence[str], None] = '5989aedcfe45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add immutable identity snapshots without losing existing reports."""
    op.add_column('student_clash_reports', sa.Column('student_registration_number_snapshot', sa.String(length=50), nullable=True))
    op.add_column('student_clash_reports', sa.Column('student_name_snapshot', sa.String(length=200), nullable=True))
    op.add_column('student_clash_reports', sa.Column('student_email_snapshot', sa.String(length=320), nullable=True))
    op.add_column('student_clash_reports', sa.Column('student_department_snapshot', sa.String(length=100), nullable=True))
    op.add_column('student_clash_reports', sa.Column('student_program_snapshot', sa.String(length=120), nullable=True))
    op.add_column('student_clash_reports', sa.Column('student_batch_snapshot', sa.String(length=40), nullable=True))
    op.add_column('student_clash_reports', sa.Column('student_semester_snapshot', sa.Integer(), nullable=True))
    op.add_column('student_clash_reports', sa.Column('student_section_snapshot', sa.String(length=50), nullable=True))
    op.add_column('student_clash_reports', sa.Column('conflict_fingerprint', sa.String(length=64), nullable=True))

    connection = op.get_bind()
    reports = sa.table(
        'student_clash_reports',
        sa.column('id', sa.Integer()),
        sa.column('student_user_id', sa.Integer()),
        sa.column('student_registration_number_snapshot', sa.String()),
        sa.column('student_name_snapshot', sa.String()),
        sa.column('student_email_snapshot', sa.String()),
        sa.column('student_department_snapshot', sa.String()),
        sa.column('student_program_snapshot', sa.String()),
        sa.column('student_batch_snapshot', sa.String()),
        sa.column('student_semester_snapshot', sa.Integer()),
        sa.column('student_section_snapshot', sa.String()),
        sa.column('conflict_fingerprint', sa.String()),
    )
    users = sa.table(
        'users',
        sa.column('id', sa.Integer()),
        sa.column('full_name', sa.String()),
        sa.column('email', sa.String()),
    )
    profiles = sa.table(
        'student_profiles',
        sa.column('user_id', sa.Integer()),
        sa.column('registration_number', sa.String()),
        sa.column('department', sa.String()),
        sa.column('program', sa.String()),
        sa.column('batch', sa.String()),
        sa.column('current_semester', sa.Integer()),
        sa.column('section', sa.String()),
    )
    rows = connection.execute(
        sa.select(
            reports.c.id,
            reports.c.student_user_id,
            users.c.full_name,
            users.c.email,
            profiles.c.registration_number,
            profiles.c.department,
            profiles.c.program,
            profiles.c.batch,
            profiles.c.current_semester,
            profiles.c.section,
        )
        .select_from(
            reports.join(users, users.c.id == reports.c.student_user_id)
            .outerjoin(profiles, profiles.c.user_id == reports.c.student_user_id)
        )
    ).mappings()
    for row in rows:
        fingerprint = hashlib.sha256(
            f"legacy-report:{row['id']}".encode('utf-8')
        ).hexdigest()
        connection.execute(
            reports.update()
            .where(reports.c.id == row['id'])
            .values(
                student_registration_number_snapshot=(
                    row['registration_number']
                    or f"LEGACY-{row['student_user_id']:08d}"
                ),
                student_name_snapshot=row['full_name'],
                student_email_snapshot=row['email'],
                student_department_snapshot=row['department'] or 'Unspecified',
                student_program_snapshot=row['program'] or 'Unspecified',
                student_batch_snapshot=row['batch'] or 'Legacy',
                student_semester_snapshot=row['current_semester'] or 1,
                student_section_snapshot=row['section'] or 'Unassigned',
                conflict_fingerprint=fingerprint,
            )
        )

    with op.batch_alter_table('student_clash_reports') as batch_op:
        for column_name, column_type in (
            ('student_registration_number_snapshot', sa.String(length=50)),
            ('student_name_snapshot', sa.String(length=200)),
            ('student_department_snapshot', sa.String(length=100)),
            ('student_program_snapshot', sa.String(length=120)),
            ('student_batch_snapshot', sa.String(length=40)),
            ('student_semester_snapshot', sa.Integer()),
            ('student_section_snapshot', sa.String(length=50)),
            ('conflict_fingerprint', sa.String(length=64)),
        ):
            batch_op.alter_column(
                column_name,
                existing_type=column_type,
                nullable=False,
            )
        batch_op.create_unique_constraint(
            'uq_student_clash_report_identity',
            ['student_user_id', 'term_id', 'conflict_fingerprint'],
        )
    op.create_index(op.f('ix_student_clash_reports_conflict_fingerprint'), 'student_clash_reports', ['conflict_fingerprint'], unique=False)


def downgrade() -> None:
    """Remove immutable report snapshots while preserving reports and items."""
    op.drop_index(op.f('ix_student_clash_reports_conflict_fingerprint'), table_name='student_clash_reports')
    with op.batch_alter_table('student_clash_reports') as batch_op:
        batch_op.drop_constraint('uq_student_clash_report_identity', type_='unique')
        batch_op.drop_column('conflict_fingerprint')
        batch_op.drop_column('student_section_snapshot')
        batch_op.drop_column('student_semester_snapshot')
        batch_op.drop_column('student_batch_snapshot')
        batch_op.drop_column('student_program_snapshot')
        batch_op.drop_column('student_department_snapshot')
        batch_op.drop_column('student_email_snapshot')
        batch_op.drop_column('student_name_snapshot')
        batch_op.drop_column('student_registration_number_snapshot')
