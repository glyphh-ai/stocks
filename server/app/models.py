"""Postgres schema for temporal glyph storage.

A GlyphVersion is one write of a symbol's glyph at a point in time (an
interval bucket). Each version fans out into GlyphNodes — one per node in the
HDC hierarchy (cortex, layers, segments, roles) — so drift can be measured at
any level by comparing the same path across versions via pgvector cosine
distance.
"""

from __future__ import annotations

from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from .hdc.core import DIM


class Base(DeclarativeBase):
    pass


class GlyphVersion(Base):
    __tablename__ = "glyph_version"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    interval: Mapped[str] = mapped_column(String(8))  # 1m, 1h, 1d, ...
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    model: Mapped[str] = mapped_column(String(64), default="")
    glyph: Mapped[dict] = mapped_column(JSONB)  # the filled instance JSON
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    nodes: Mapped[list["GlyphNode"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )

    __table_args__ = (
        UniqueConstraint("symbol", "interval", "ts", name="uq_version_bucket"),
    )


class GlyphNode(Base):
    __tablename__ = "glyph_node"

    id: Mapped[int] = mapped_column(primary_key=True)
    version_id: Mapped[int] = mapped_column(
        ForeignKey("glyph_version.id", ondelete="CASCADE"), index=True
    )
    level: Mapped[str] = mapped_column(String(8))  # cortex | layer | segment | role
    path: Mapped[str] = mapped_column(String(255))  # full node key, e.g. role:symbol/price_action/price
    vec: Mapped[list[float]] = mapped_column(Vector(DIM))

    version: Mapped["GlyphVersion"] = relationship(back_populates="nodes")

    __table_args__ = (Index("ix_node_version_path", "version_id", "path"),)


class GlyphTemplate(Base):
    """A saved glyph structure built in the config UI. The instance template
    (layers/segments/roles/jobs) that jobs fill and persist as versions."""

    __tablename__ = "glyph_template"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    symbol: Mapped[str] = mapped_column(String(32), default="")
    body: Mapped[dict] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Credential(Base):
    """An encrypted secret a tool step can reference by name.

    `kind` is the credential shape (bearer | basic | header); `enc` is the
    Fernet-encrypted JSON of the secret fields for that kind. The plaintext is
    only decrypted server-side in the job runner — it is never sent to the UI.
    """

    __tablename__ = "credential"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(16))  # bearer | basic | header
    enc: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
