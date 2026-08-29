"""repair academic term postgres sequence

Revision ID: f3c1b6a9d742
Revises: a8479a74c680
Create Date: 2026-08-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "f3c1b6a9d742"
down_revision: Union[str, Sequence[str], None] = "a8479a74c680"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Align PostgreSQL's academic term sequence with existing rows."""
    bind = op.get_bind()

    if bind.dialect.name != "postgresql":
        return

    op.execute(
        sa.text(
            """
            SELECT setval(
                pg_get_serial_sequence('academic_terms', 'id'),
                COALESCE((SELECT MAX(id) FROM academic_terms), 1),
                EXISTS (SELECT 1 FROM academic_terms)
            )
            """
        )
    )


def downgrade() -> None:
    """Sequence alignment is intentionally not reversed."""
    pass
