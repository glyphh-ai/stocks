"""initial glyph schema

Revision ID: 0001
Revises:
Create Date: 2026-06-05
"""

from typing import Sequence, Union

import pgvector.sqlalchemy
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from app.hdc.core import DIM

revision: str = "0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "glyph_version",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model", sa.String(length=64), nullable=False),
        sa.Column("glyph", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("symbol", "interval", "ts", name="uq_version_bucket"),
    )
    op.create_index("ix_glyph_version_symbol", "glyph_version", ["symbol"])
    op.create_index("ix_glyph_version_ts", "glyph_version", ["ts"])

    op.create_table(
        "glyph_node",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "version_id",
            sa.Integer(),
            sa.ForeignKey("glyph_version.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("level", sa.String(length=8), nullable=False),
        sa.Column("path", sa.String(length=255), nullable=False),
        sa.Column("vec", pgvector.sqlalchemy.Vector(DIM), nullable=False),
    )
    op.create_index("ix_glyph_node_version_id", "glyph_node", ["version_id"])
    op.create_index("ix_node_version_path", "glyph_node", ["version_id", "path"])


def downgrade() -> None:
    op.drop_table("glyph_node")
    op.drop_table("glyph_version")
