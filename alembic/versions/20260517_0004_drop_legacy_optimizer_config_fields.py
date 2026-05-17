"""drop legacy optimizer config fields (model_id, rounds, gp_profile)

These three columns were carried over from an earlier gradient-based optimizer era.
The current Leo optimizer only uses llm_provider / llm_model / llm_base_url /
llm_timeout_seconds / llm_api_token_encrypted and does not read the removed columns.

Revision ID: 20260517_0011
Revises: 20260517_0010
Create Date: 2026-05-17 00:00:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

from alembic import op

revision: str = "20260517_0011"
down_revision: str | None = "20260517_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)  # type: ignore[arg-type]
    existing = {c["name"] for c in inspector.get_columns("configs")}

    cols_to_drop = [c for c in ("model_id", "rounds", "gp_profile") if c in existing]
    if cols_to_drop:
        with op.batch_alter_table("configs") as batch_op:
            for col in cols_to_drop:
                batch_op.drop_column(col)


def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)  # type: ignore[arg-type]
    existing = {c["name"] for c in inspector.get_columns("configs")}

    with op.batch_alter_table("configs") as batch_op:
        if "model_id" not in existing:
            batch_op.add_column(sa.Column("model_id", sa.String(), nullable=True))
        if "rounds" not in existing:
            batch_op.add_column(sa.Column("rounds", sa.Integer(), nullable=True))
        if "gp_profile" not in existing:
            batch_op.add_column(sa.Column("gp_profile", sa.String(), nullable=True))
