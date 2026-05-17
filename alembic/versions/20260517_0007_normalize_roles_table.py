"""normalize user roles into dedicated table

Revision ID: 20260517_0007
Revises: 20260517_0006
Create Date: 2026-05-17 14:10:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260517_0007"
down_revision: str | None = "20260517_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.CheckConstraint("trim(name) <> ''", name="ck_roles_name_not_blank"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_roles_name"),
    )
    op.create_index(op.f("ix_roles_id"), "roles", ["id"], unique=False)
    op.create_index(op.f("ix_roles_name"), "roles", ["name"], unique=False)

    conn = op.get_bind()
    conn.execute(sa.text("INSERT INTO roles (name) VALUES ('admin'), ('developer')"))

    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("role_id", sa.Integer(), nullable=True))

    conn.execute(
        sa.text(
            """
            UPDATE users
            SET role_id = (
                SELECT roles.id FROM roles WHERE lower(roles.name) = lower(users.role)
            )
            """
        )
    )

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_constraint("ck_users_role_valid", type_="check")
        batch_op.create_foreign_key("fk_users_role_id_roles", "roles", ["role_id"], ["id"], ondelete="RESTRICT")
        batch_op.alter_column("role_id", existing_type=sa.Integer(), nullable=False)
        batch_op.create_index("ix_users_role_id", ["role_id"], unique=False)
        batch_op.drop_column("role")


def downgrade() -> None:
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("role", sa.String(), nullable=True))

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE users
            SET role = (
                SELECT roles.name FROM roles WHERE roles.id = users.role_id
            )
            """
        )
    )

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_index("ix_users_role_id")
        batch_op.drop_constraint("fk_users_role_id_roles", type_="foreignkey")
        batch_op.alter_column("role", existing_type=sa.String(), nullable=False)
        batch_op.create_check_constraint("ck_users_role_valid", "role in ('admin', 'developer')")
        batch_op.drop_column("role_id")

    op.drop_index(op.f("ix_roles_name"), table_name="roles")
    op.drop_index(op.f("ix_roles_id"), table_name="roles")
    op.drop_table("roles")