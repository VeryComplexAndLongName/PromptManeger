"""initial with tags and versioning

Revision ID: 20260424_0001
Revises:
Create Date: 2026-04-24 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import inspect

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260424_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "prompts" not in tables:
        op.create_table(
            "prompts",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(), nullable=True),
            sa.Column("project", sa.String(), nullable=True),
            sa.UniqueConstraint("name", "project", name="uq_prompt_name_project"),
        )
        op.create_index(op.f("ix_prompts_id"), "prompts", ["id"], unique=False)
        op.create_index(op.f("ix_prompts_name"), "prompts", ["name"], unique=False)
        op.create_index(op.f("ix_prompts_project"), "prompts", ["project"], unique=False)
    else:
        op.execute("CREATE INDEX IF NOT EXISTS ix_prompts_name ON prompts (name)")
        op.execute("CREATE INDEX IF NOT EXISTS ix_prompts_project ON prompts (project)")

    if "tags" not in tables:
        op.create_table(
            "tags",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("name", sa.String(), nullable=False),
            sa.UniqueConstraint("name"),
        )
        op.create_index(op.f("ix_tags_id"), "tags", ["id"], unique=False)
        op.create_index(op.f("ix_tags_name"), "tags", ["name"], unique=True)
    else:
        op.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_tags_name ON tags (name)")

    if "prompt_versions" not in tables:
        op.create_table(
            "prompt_versions",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("prompt_id", sa.Integer(), sa.ForeignKey("prompts.id", ondelete="CASCADE"), nullable=True),
            sa.Column("version", sa.Integer(), nullable=True),
            sa.Column("content", sa.Text(), nullable=True),
            sa.UniqueConstraint("prompt_id", "version", name="uq_prompt_version"),
        )
        op.create_index(op.f("ix_prompt_versions_id"), "prompt_versions", ["id"], unique=False)
    else:
        op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_prompt_version ON prompt_versions (prompt_id, version)")

    if "prompt_tags" not in tables:
        op.create_table(
            "prompt_tags",
            sa.Column("prompt_id", sa.Integer(), sa.ForeignKey("prompts.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("tag_id", sa.Integer(), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    tables = set(inspector.get_table_names())

    if "prompt_tags" in tables:
        op.drop_table("prompt_tags")
    if "prompt_versions" in tables:
        op.drop_index(op.f("ix_prompt_versions_id"), table_name="prompt_versions")
        op.drop_table("prompt_versions")
    if "tags" in tables:
        op.drop_index(op.f("ix_tags_name"), table_name="tags")
        op.drop_index(op.f("ix_tags_id"), table_name="tags")
        op.drop_table("tags")
    if "prompts" in tables:
        op.drop_index(op.f("ix_prompts_project"), table_name="prompts")
        op.drop_index(op.f("ix_prompts_name"), table_name="prompts")
        op.drop_index(op.f("ix_prompts_id"), table_name="prompts")
        op.drop_table("prompts")
