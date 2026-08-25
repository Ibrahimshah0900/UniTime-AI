"""add verified student provisioning

Revision ID: 5989aedcfe45
Revises: 8ff39f7b22e6
Create Date: 2026-08-25 05:18:55.165375

"""
from datetime import UTC, datetime
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5989aedcfe45'
down_revision: Union[str, Sequence[str], None] = '8ff39f7b22e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add institution-controlled student identity and onboarding state."""
    op.create_table('student_profiles',
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('registration_number', sa.String(length=50), nullable=False),
    sa.Column('department', sa.String(length=100), nullable=False),
    sa.Column('program', sa.String(length=120), nullable=False),
    sa.Column('batch', sa.String(length=40), nullable=False),
    sa.Column('current_semester', sa.Integer(), nullable=False),
    sa.Column('section', sa.String(length=50), nullable=False),
    sa.Column('academic_status', sa.String(length=20), server_default='active', nullable=False),
    sa.Column('is_verified', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('preferred_name', sa.String(length=100), nullable=True),
    sa.Column('onboarding_completed', sa.Boolean(), server_default='0', nullable=False),
    sa.Column('created_by_user_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.CheckConstraint("academic_status IN ('active','on_leave','graduated','suspended')", name='ck_student_profiles_academic_status'),
    sa.CheckConstraint('current_semester >= 1 AND current_semester <= 16', name='ck_student_profiles_current_semester'),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('user_id'),
    sa.UniqueConstraint('registration_number')
    )
    op.add_column(
        'users',
        sa.Column(
            'must_change_password',
            sa.Boolean(),
            server_default='0',
            nullable=False,
        ),
    )
    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'email',
            existing_type=sa.VARCHAR(length=320),
            nullable=True,
        )

    # Preserve existing student accounts without pretending their generated
    # migration identity has been institutionally verified. Coordinators can
    # correct and verify these profiles through the provisioning API.
    connection = op.get_bind()
    users = sa.table(
        'users',
        sa.column('id', sa.Integer()),
        sa.column('role', sa.String()),
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
        sa.column('academic_status', sa.String()),
        sa.column('is_verified', sa.Boolean()),
        sa.column('onboarding_completed', sa.Boolean()),
        sa.column('created_at', sa.DateTime()),
        sa.column('updated_at', sa.DateTime()),
    )
    now = datetime.now(UTC).replace(tzinfo=None)
    student_ids = connection.execute(
        sa.select(users.c.id).where(users.c.role == 'student')
    ).scalars()
    rows = [
        {
            'user_id': user_id,
            'registration_number': f'LEGACY-{user_id:08d}',
            'department': 'Unspecified',
            'program': 'Unspecified',
            'batch': 'Legacy',
            'current_semester': 1,
            'section': 'Unassigned',
            'academic_status': 'active',
            'is_verified': False,
            'onboarding_completed': True,
            'created_at': now,
            'updated_at': now,
        }
        for user_id in student_ids
    ]
    if rows:
        op.bulk_insert(profiles, rows)


def downgrade() -> None:
    """Restore the pre-provisioning user schema without dropping users."""
    op.drop_table('student_profiles')

    # The previous schema required an email. A rollback-only placeholder keeps
    # registration-number-only accounts recoverable instead of deleting them.
    connection = op.get_bind()
    users = sa.table(
        'users',
        sa.column('id', sa.Integer()),
        sa.column('email', sa.String()),
    )
    missing_email_ids = connection.execute(
        sa.select(users.c.id).where(users.c.email.is_(None))
    ).scalars()
    for user_id in missing_email_ids:
        connection.execute(
            users.update()
            .where(users.c.id == user_id)
            .values(email=f'rollback-user-{user_id}@invalid.local')
        )

    with op.batch_alter_table('users') as batch_op:
        batch_op.alter_column(
            'email',
            existing_type=sa.VARCHAR(length=320),
            nullable=False,
        )
        batch_op.drop_column('must_change_password')
