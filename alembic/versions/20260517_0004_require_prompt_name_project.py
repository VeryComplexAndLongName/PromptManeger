"""require non-empty prompt name and project

Revision ID: 20260517_0004
Revises: 20260426_0003
Create Date: 2026-05-17 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260517_0004"
down_revision: str | None = "20260426_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "prompts"
NAME_CHECK = "ck_prompts_name_not_blank"
PROJECT_CHECK = "ck_prompts_project_not_blank"


def _backfill_invalid_prompt_rows() -> None:
    conn = op.get_bind()
    invalid_count = conn.execute(
        sa.text(
            """
            SELECT COUNT(*)
            FROM prompts
            WHERE name IS NULL
               OR project IS NULL
               OR trim(name) = ''
               OR trim(project) = ''
            """
        )
    ).scalar_one()

    if invalid_count:
        conn.execute(
            sa.text(
                """
                UPDATE prompts
                SET
                    name = CASE
                        WHEN name IS NULL OR trim(name) = '' THEN 'unnamed-prompt-' || id
                        ELSE trim(name)
                    END,
                    project = CASE
                        WHEN project IS NULL OR trim(project) = '' THEN 'legacy-project'
                        ELSE trim(project)
                    END
                WHERE name IS NULL
                   OR project IS NULL
                   OR trim(name) = ''
                   OR trim(project) = ''
                """
            )
        )


def upgrade() -> None:
    _backfill_invalid_prompt_rows()

    with op.batch_alter_table(TABLE_NAME) as batch_op:
        batch_op.alter_column("name", existing_type=sa.String(), nullable=False)
        batch_op.alter_column("project", existing_type=sa.String(), nullable=False)
        batch_op.create_check_constraint(NAME_CHECK, "trim(name) <> ''")
        batch_op.create_check_constraint(PROJECT_CHECK, "trim(project) <> ''")


def downgrade() -> None:
    with op.batch_alter_table(TABLE_NAME) as batch_op:
        batch_op.drop_constraint(PROJECT_CHECK, type_="check")
        batch_op.drop_constraint(NAME_CHECK, type_="check")
        batch_op.alter_column("project", existing_type=sa.String(), nullable=True)
        batch_op.alter_column("name", existing_type=sa.String(), nullable=True)
