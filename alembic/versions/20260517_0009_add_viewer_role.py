"""add viewer role

Revision ID: 20260517_0009
Revises: 20260517_0008
Create Date: 2026-05-17 19:05:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260517_0009"
down_revision: str | None = "20260517_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO roles (name)
            SELECT 'viewer'
            WHERE NOT EXISTS (
                SELECT 1 FROM roles WHERE lower(name) = 'viewer'
            )
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM roles WHERE lower(name) = 'viewer'"))
