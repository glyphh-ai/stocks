"""ensemble glyph predictions (predicted next-interval glyphs)

Revision ID: 0006
Revises: 0005
Create Date: 2026-06-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "glyph_prediction",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False),
        sa.Column("target_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon", sa.String(length=8), nullable=False),
        sa.Column("basis_versions", sa.Integer(), nullable=False),
        sa.Column("glyph", JSONB(), nullable=False),
        sa.Column("components", JSONB(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint(
            "symbol", "interval", "target_ts", name="uq_prediction_bucket"
        ),
    )
    op.create_index(
        "ix_glyph_prediction_symbol", "glyph_prediction", ["symbol"]
    )
    op.create_index(
        "ix_glyph_prediction_target_ts", "glyph_prediction", ["target_ts"]
    )


def downgrade() -> None:
    op.drop_index("ix_glyph_prediction_target_ts", table_name="glyph_prediction")
    op.drop_index("ix_glyph_prediction_symbol", table_name="glyph_prediction")
    op.drop_table("glyph_prediction")
