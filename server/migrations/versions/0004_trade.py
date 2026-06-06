"""trade records aligned to glyph versions

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-06
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, Sequence[str], None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "trade",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False, server_default="open"),
        sa.Column("entry_ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_price", sa.Float(), nullable=False),
        sa.Column("volume", sa.Float(), nullable=False),
        sa.Column("stop", sa.Float(), nullable=True),
        sa.Column(
            "entry_version_id",
            sa.Integer(),
            sa.ForeignKey("glyph_version.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("exit_ts", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_price", sa.Float(), nullable=True),
        sa.Column(
            "exit_version_id",
            sa.Integer(),
            sa.ForeignKey("glyph_version.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("pnl", sa.Float(), nullable=True),
        sa.Column("notes", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_trade_symbol", "trade", ["symbol"])
    op.create_index("ix_trade_entry_ts", "trade", ["entry_ts"])


def downgrade() -> None:
    op.drop_table("trade")
