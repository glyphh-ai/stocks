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
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
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


class GlyphPrediction(Base):
    """A projected next-interval glyph, the output of the ensemble predictor.

    Unlike GlyphVersion (a recorded *actual* snapshot), this is a *predicted*
    one. `horizon` separates the walk-forward history rows — one predicted glyph
    per past interval, predicted only from prior history — from the single
    `ahead` row that projects the next, not-yet-printed interval. `components`
    holds the per-signal contribution of each ensemble source (autoregressive,
    beam, trades, llm) so a prediction can be explained and later scored against
    what actually printed. Predictions are derived, so a refresh wipes and
    rebuilds the whole set for a symbol/interval.
    """

    __tablename__ = "glyph_prediction"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    interval: Mapped[str] = mapped_column(String(8))
    target_ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )  # the interval being predicted
    horizon: Mapped[str] = mapped_column(String(8))  # history | ahead
    basis_versions: Mapped[int] = mapped_column()  # history points used
    glyph: Mapped[dict] = mapped_column(JSONB)  # the projected instance JSON
    components: Mapped[dict] = mapped_column(JSONB)  # per-signal source breakdown
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint(
            "symbol", "interval", "target_ts", name="uq_prediction_bucket"
        ),
    )


class PredictionConversation(Base):
    """The running Claude dialogue that shapes a symbol/interval's forecasts.

    The LLM forecaster does not start cold each interval — it continues one
    persistent conversation per (symbol, interval). `messages` is the full
    Anthropic messages array (every content block, including any server-side
    compaction blocks) carried from one prediction to the next, so the model's
    reasoning about regime, signal couplings, and how its past calls fared
    accumulates over time. Compaction keeps it from growing without bound.
    """

    __tablename__ = "prediction_conversation"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    interval: Mapped[str] = mapped_column(String(8))
    messages: Mapped[list] = mapped_column(JSONB, default=list)  # Anthropic msgs
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        UniqueConstraint("symbol", "interval", name="uq_conversation_bucket"),
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


class Trade(Base):
    """A real trade the user pushed through their platform, recorded against
    the glyph history.

    The entry and (later) the exit each pin to the nearest glyph version at
    their timestamp (entry_version_id / exit_version_id), so every trade is
    aligned to the full HDC snapshot of market conditions at that moment. P&L
    is realized only once the trade is closed.
    """

    __tablename__ = "trade"

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(32), index=True)
    interval: Mapped[str] = mapped_column(String(8))
    side: Mapped[str] = mapped_column(String(8))  # long | short
    status: Mapped[str] = mapped_column(String(8), default="open")  # open | closed

    entry_ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    entry_price: Mapped[float] = mapped_column(Float)
    volume: Mapped[float] = mapped_column(Float)
    stop: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("glyph_version.id", ondelete="SET NULL"), nullable=True
    )

    exit_ts: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    exit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    exit_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("glyph_version.id", ondelete="SET NULL"), nullable=True
    )
    pnl: Mapped[float | None] = mapped_column(Float, nullable=True)  # gross

    # Platform costs, snapshotted from settings at the time of each leg. net_pnl
    # is the gross pnl less both legs' fees, set when the trade closes.
    entry_fee: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    exit_fee: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    net_pnl: Mapped[float | None] = mapped_column(Float, nullable=True)

    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AppSettings(Base):
    """Singleton (id=1) application settings.

    Trade-fee config mirrors how a brokerage charges, applied per leg: a flat
    commission, a per-share rate, and a percent of notional. Net P&L on each
    trade subtracts the resulting entry and exit fees from the gross.
    """

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    commission_per_trade: Mapped[float] = mapped_column(
        Float, default=0.0, server_default="0"
    )
    per_share: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    percent: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
