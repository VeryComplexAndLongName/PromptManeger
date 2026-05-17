"""add auth, config, and RBAC tables

Revision ID: 20260517_0005
Revises: 20260517_0004
Create Date: 2026-05-17 00:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260517_0005"
down_revision: str | None = "20260517_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(), nullable=False),
        sa.Column("password_hash_encrypted", sa.Text(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.CheckConstraint("trim(username) <> ''", name="ck_users_username_not_blank"),
        sa.CheckConstraint("role in ('admin', 'developer')", name="ck_users_role_valid"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index(op.f("ix_users_id"), "users", ["id"], unique=False)
    op.create_index(op.f("ix_users_username"), "users", ["username"], unique=False)

    op.create_table(
        "configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("model_id", sa.String(), nullable=True),
        sa.Column("rounds", sa.Integer(), nullable=True),
        sa.Column("gp_profile", sa.String(), nullable=True),
        sa.Column("llm_provider", sa.String(), nullable=True),
        sa.Column("llm_model", sa.String(), nullable=True),
        sa.Column("llm_base_url", sa.String(), nullable=True),
        sa.Column("llm_timeout_seconds", sa.Integer(), nullable=True),
        sa.Column("llm_api_token_encrypted", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_configs_user_id"),
    )
    op.create_index(op.f("ix_configs_id"), "configs", ["id"], unique=False)

    op.create_table(
        "project_access",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project", sa.String(), nullable=False),
        sa.CheckConstraint("trim(project) <> ''", name="ck_project_access_project_not_blank"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "project", name="uq_project_access_user_project"),
    )
    op.create_index(op.f("ix_project_access_id"), "project_access", ["id"], unique=False)
    op.create_index(op.f("ix_project_access_project"), "project_access", ["project"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_project_access_project"), table_name="project_access")
    op.drop_index(op.f("ix_project_access_id"), table_name="project_access")
    op.drop_table("project_access")

    op.drop_index(op.f("ix_configs_id"), table_name="configs")
    op.drop_table("configs")

    op.drop_index(op.f("ix_users_username"), table_name="users")
    op.drop_index(op.f("ix_users_id"), table_name="users")
    op.drop_table("users")