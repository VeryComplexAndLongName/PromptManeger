"""backfill legacy prompt audit authors

Revision ID: 20260517_0010
Revises: 20260517_0009
Create Date: 2026-05-17 20:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260517_0010"
down_revision: str | None = "20260517_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE prompts
            SET created_by_id = (SELECT id FROM users WHERE lower(username) = 'admin' LIMIT 1)
            WHERE created_by_id IS NULL
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE prompts
            SET updated_by_id = (SELECT id FROM users WHERE lower(username) = 'admin' LIMIT 1)
            WHERE updated_by_id IS NULL
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE prompt_versions
            SET created_by_id = (SELECT id FROM users WHERE lower(username) = 'admin' LIMIT 1)
            WHERE created_by_id IS NULL
            """
        )
    )


def downgrade() -> None:
    conn = op.get_bind()
    admin_id = conn.execute(sa.text("SELECT id FROM users WHERE lower(username) = 'admin' LIMIT 1")).scalar()
    if admin_id is None:
        return

    conn.execute(sa.text("UPDATE prompts SET created_by_id = NULL WHERE created_by_id = :admin_id"), {"admin_id": admin_id})
    conn.execute(sa.text("UPDATE prompts SET updated_by_id = NULL WHERE updated_by_id = :admin_id"), {"admin_id": admin_id})
    conn.execute(sa.text("UPDATE prompt_versions SET created_by_id = NULL WHERE created_by_id = :admin_id"), {"admin_id": admin_id})
