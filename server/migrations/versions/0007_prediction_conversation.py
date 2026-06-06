"""persistent LLM forecasting conversation per symbol/interval

Revision ID: 0007
Revises: 0006
Create Date: 2026-06-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0007"
down_revision: Union[str, Sequence[str], None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "prediction_conversation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False),
        sa.Column("messages", JSONB(), nullable=False, server_default="[]"),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()
        ),
        sa.UniqueConstraint(
            "symbol", "interval", name="uq_conversation_bucket"
        ),
    )
    op.create_index(
        "ix_prediction_conversation_symbol", "prediction_conversation", ["symbol"]
    )


def downgrade() -> None:
    op.drop_index(
        "ix_prediction_conversation_symbol",
        table_name="prediction_conversation",
    )
    op.drop_table("prediction_conversation")
