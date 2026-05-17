"""normalize projects into dedicated table

Revision ID: 20260517_0006
Revises: 20260517_0005
Create Date: 2026-05-17 13:40:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260517_0006"
down_revision: str | None = "20260517_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.CheckConstraint("trim(name) <> ''", name="ck_projects_name_not_blank"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_projects_name"),
    )
    op.create_index(op.f("ix_projects_id"), "projects", ["id"], unique=False)
    op.create_index(op.f("ix_projects_name"), "projects", ["name"], unique=False)

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            INSERT INTO projects (name)
            SELECT project_name FROM (
                SELECT DISTINCT trim(project) AS project_name FROM prompts WHERE project IS NOT NULL AND trim(project) <> ''
                UNION
                SELECT DISTINCT trim(project) AS project_name FROM project_access WHERE project IS NOT NULL AND trim(project) <> ''
            ) AS names
            """
        )
    )

    with op.batch_alter_table("prompts") as batch_op:
        batch_op.add_column(sa.Column("project_id", sa.Integer(), nullable=True))

    with op.batch_alter_table("project_access") as batch_op:
        batch_op.add_column(sa.Column("project_id", sa.Integer(), nullable=True))

    conn.execute(
        sa.text(
            """
            UPDATE prompts
            SET project_id = (
                SELECT projects.id FROM projects WHERE projects.name = prompts.project
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE project_access
            SET project_id = (
                SELECT projects.id FROM projects WHERE projects.name = project_access.project
            )
            """
        )
    )

    with op.batch_alter_table("prompts") as batch_op:
        batch_op.drop_constraint("uq_prompt_name_project", type_="unique")
        batch_op.drop_constraint("ck_prompts_project_not_blank", type_="check")
        batch_op.drop_index("ix_prompts_project")
        batch_op.create_foreign_key("fk_prompts_project_id_projects", "projects", ["project_id"], ["id"], ondelete="CASCADE")
        batch_op.alter_column("project_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("project")
        batch_op.create_unique_constraint("uq_prompt_name_project_id", ["name", "project_id"])
        batch_op.create_index("ix_prompts_project_id", ["project_id"], unique=False)

    with op.batch_alter_table("project_access") as batch_op:
        batch_op.drop_constraint("uq_project_access_user_project", type_="unique")
        batch_op.drop_constraint("ck_project_access_project_not_blank", type_="check")
        batch_op.drop_index("ix_project_access_project")
        batch_op.create_foreign_key("fk_project_access_project_id_projects", "projects", ["project_id"], ["id"], ondelete="CASCADE")
        batch_op.alter_column("project_id", existing_type=sa.Integer(), nullable=False)
        batch_op.drop_column("project")
        batch_op.create_unique_constraint("uq_project_access_user_project_id", ["user_id", "project_id"])
        batch_op.create_index("ix_project_access_project_id", ["project_id"], unique=False)


def downgrade() -> None:
    with op.batch_alter_table("project_access") as batch_op:
        batch_op.add_column(sa.Column("project", sa.String(), nullable=True))

    with op.batch_alter_table("prompts") as batch_op:
        batch_op.add_column(sa.Column("project", sa.String(), nullable=True))

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE prompts
            SET project = (
                SELECT projects.name FROM projects WHERE projects.id = prompts.project_id
            )
            """
        )
    )
    conn.execute(
        sa.text(
            """
            UPDATE project_access
            SET project = (
                SELECT projects.name FROM projects WHERE projects.id = project_access.project_id
            )
            """
        )
    )

    with op.batch_alter_table("prompts") as batch_op:
        batch_op.drop_index("ix_prompts_project_id")
        batch_op.drop_constraint("uq_prompt_name_project_id", type_="unique")
        batch_op.drop_constraint("fk_prompts_project_id_projects", type_="foreignkey")
        batch_op.alter_column("project", existing_type=sa.String(), nullable=False)
        batch_op.create_check_constraint("ck_prompts_project_not_blank", "trim(project) <> ''")
        batch_op.create_unique_constraint("uq_prompt_name_project", ["name", "project"])
        batch_op.create_index("ix_prompts_project", ["project"], unique=False)
        batch_op.drop_column("project_id")

    with op.batch_alter_table("project_access") as batch_op:
        batch_op.drop_index("ix_project_access_project_id")
        batch_op.drop_constraint("uq_project_access_user_project_id", type_="unique")
        batch_op.drop_constraint("fk_project_access_project_id_projects", type_="foreignkey")
        batch_op.alter_column("project", existing_type=sa.String(), nullable=False)
        batch_op.create_check_constraint("ck_project_access_project_not_blank", "trim(project) <> ''")
        batch_op.create_unique_constraint("uq_project_access_user_project", ["user_id", "project"])
        batch_op.create_index("ix_project_access_project", ["project"], unique=False)
        batch_op.drop_column("project_id")

    op.drop_index(op.f("ix_projects_name"), table_name="projects")
    op.drop_index(op.f("ix_projects_id"), table_name="projects")
    op.drop_table("projects")