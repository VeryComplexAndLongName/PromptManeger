import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

from alembic import op

revision = "20260426_0002"
down_revision = "20260424_0001"

def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)  # type: ignore[arg-type]
    existing_columns = [c["name"] for c in inspector.get_columns("prompt_versions")]

    # Add new columns as nullable first, if they don't already exist
    for col_name, col_type in [
        ("role", sa.String()),
        ("task", sa.Text()),
        ("context", sa.Text()),
        ("constraints", sa.Text()),
        ("output_format", sa.Text()),
        ("examples", sa.Text()),
    ]:
        if col_name not in existing_columns:
            op.add_column("prompt_versions", sa.Column(col_name, col_type, nullable=True))

    # Migration data from content to task
    op.execute("UPDATE prompt_versions SET task = content WHERE task IS NULL AND content IS NOT NULL")

    # Use batch_alter_table for SQLite compatibility
    with op.batch_alter_table("prompt_versions") as batch_op:
        batch_op.alter_column("task", existing_type=sa.Text(), nullable=False)
        if "content" in existing_columns:
            batch_op.drop_column("content")

def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)  # type: ignore[arg-type]
    existing_columns = [c["name"] for c in inspector.get_columns("prompt_versions")]

    if "content" not in existing_columns:
        op.add_column("prompt_versions", sa.Column("content", sa.Text(), nullable=True))

    op.execute("UPDATE prompt_versions SET content = task WHERE content IS NULL AND task IS NOT NULL")

    with op.batch_alter_table("prompt_versions") as batch_op:
        batch_op.alter_column("content", existing_type=sa.Text(), nullable=False)
        for col in ["examples", "output_format", "constraints", "context", "task", "role"]:
            if col in [c["name"] for c in inspector.get_columns("prompt_versions")]:
                batch_op.drop_column(col)
