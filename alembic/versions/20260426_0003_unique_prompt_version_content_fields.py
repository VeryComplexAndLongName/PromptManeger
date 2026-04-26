"""add unique index for prompt version content fields

Revision ID: 20260426_0003
Revises: 20260426_0002
Create Date: 2026-04-26 09:20:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260426_0003"
down_revision: str | None = "20260426_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


INDEX_NAME = "uq_prompt_version_content_fields"
TABLE_NAME = "prompt_versions"


def _raise_if_duplicates_exist() -> None:
    conn = op.get_bind()
    duplicates = conn.execute(
        sa.text(
            """
            SELECT
                role,
                task,
                context,
                constraints,
                output_format,
                examples,
                COUNT(*) AS cnt
            FROM prompt_versions
            GROUP BY role, task, context, constraints, output_format, examples
            HAVING COUNT(*) > 1
            LIMIT 5
            """
        )
    ).fetchall()

    if duplicates:
        sample = [dict(row._mapping) for row in duplicates]
        raise RuntimeError(
            "Cannot create unique index on prompt_versions content fields: "
            f"found duplicate rows. Sample: {sample}. "
            "Please deduplicate existing data before re-running migration."
        )


def upgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)

    existing_indexes = {idx["name"] for idx in inspector.get_indexes(TABLE_NAME)}
    if INDEX_NAME in existing_indexes:
        return

    _raise_if_duplicates_exist()
    op.create_index(
        INDEX_NAME,
        TABLE_NAME,
        ["role", "task", "context", "constraints", "output_format", "examples"],
        unique=True,
    )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_indexes = {idx["name"] for idx in inspector.get_indexes(TABLE_NAME)}

    if INDEX_NAME in existing_indexes:
        op.drop_index(INDEX_NAME, table_name=TABLE_NAME)
