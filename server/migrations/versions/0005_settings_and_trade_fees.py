"""app settings (trade fees) + per-trade fee columns

Revision ID: 0005
Revises: 0004
Create Date: 2026-06-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "commission_per_trade", sa.Float(), nullable=False, server_default="0"
        ),
        sa.Column("per_share", sa.Float(), nullable=False, server_default="0"),
        sa.Column("percent", sa.Float(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        "INSERT INTO app_settings (id, commission_per_trade, per_share, percent) "
        "VALUES (1, 0, 0, 0)"
    )

    op.add_column(
        "trade",
        sa.Column("entry_fee", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "trade",
        sa.Column("exit_fee", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column("trade", sa.Column("net_pnl", sa.Float(), nullable=True))


def downgrade() -> None:
    op.drop_column("trade", "net_pnl")
    op.drop_column("trade", "exit_fee")
    op.drop_column("trade", "entry_fee")
    op.drop_table("app_settings")
