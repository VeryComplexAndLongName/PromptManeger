"""add prompt audit metadata columns

Revision ID: 20260517_0008
Revises: 20260517_0007
Create Date: 2026-05-17 18:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260517_0008"
down_revision: str | None = "20260517_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("prompts") as batch_op:
        batch_op.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("created_by_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("updated_by_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_prompts_created_by_id", ["created_by_id"], unique=False)
        batch_op.create_index("ix_prompts_updated_by_id", ["updated_by_id"], unique=False)
        batch_op.create_foreign_key("fk_prompts_created_by_id_users", "users", ["created_by_id"], ["id"], ondelete="SET NULL")
        batch_op.create_foreign_key("fk_prompts_updated_by_id_users", "users", ["updated_by_id"], ["id"], ondelete="SET NULL")

    with op.batch_alter_table("prompt_versions") as batch_op:
        batch_op.add_column(sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("created_by_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_prompt_versions_created_by_id", ["created_by_id"], unique=False)
        batch_op.create_foreign_key("fk_prompt_versions_created_by_id_users", "users", ["created_by_id"], ["id"], ondelete="SET NULL")

    conn = op.get_bind()
    conn.execute(sa.text("UPDATE prompts SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
    conn.execute(sa.text("UPDATE prompts SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL"))
    conn.execute(sa.text("UPDATE prompt_versions SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))

    with op.batch_alter_table("prompts") as batch_op:
        batch_op.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=False)
        batch_op.alter_column("updated_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    with op.batch_alter_table("prompt_versions") as batch_op:
        batch_op.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("prompt_versions") as batch_op:
        batch_op.drop_constraint("fk_prompt_versions_created_by_id_users", type_="foreignkey")
        batch_op.drop_index("ix_prompt_versions_created_by_id")
        batch_op.drop_column("created_by_id")
        batch_op.drop_column("created_at")

    with op.batch_alter_table("prompts") as batch_op:
        batch_op.drop_constraint("fk_prompts_updated_by_id_users", type_="foreignkey")
        batch_op.drop_constraint("fk_prompts_created_by_id_users", type_="foreignkey")
        batch_op.drop_index("ix_prompts_updated_by_id")
        batch_op.drop_index("ix_prompts_created_by_id")
        batch_op.drop_column("updated_by_id")
        batch_op.drop_column("created_by_id")
        batch_op.drop_column("updated_at")
        batch_op.drop_column("created_at")
