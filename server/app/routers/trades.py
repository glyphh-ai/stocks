"""Record real trades against the glyph history.

POST   /trades             -> open a trade (entry leg); pins entry_version_id
POST   /trades/{id}/close  -> record the exit leg; computes realized P&L
GET    /trades             -> list trades (optionally filtered by symbol/interval)
GET    /trades/{id}        -> one trade
DELETE /trades/{id}        -> remove a trade

Each leg is aligned to the nearest glyph version at its timestamp, so a trade
correlates to the full HDC snapshot of conditions at entry and exit.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..analysis import analyze_trade
from ..db import PgSession
from ..models import Trade
from ..storage import version_at_ts

router = APIRouter(prefix="/trades", tags=["trades"])


class TradeOpen(BaseModel):
    symbol: str
    interval: str = "1d"
    side: str = "long"  # long | short
    entry_ts: datetime
    entry_price: float
    volume: float
    stop: float | None = None
    notes: str | None = None


class TradeClose(BaseModel):
    exit_ts: datetime
    exit_price: float
    notes: str | None = None


class TradeOut(BaseModel):
    id: int
    symbol: str
    interval: str
    side: str
    status: str
    entry_ts: datetime
    entry_price: float
    volume: float
    stop: float | None
    entry_version_id: int | None
    exit_ts: datetime | None
    exit_price: float | None
    exit_version_id: int | None
    pnl: float | None
    notes: str | None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


def _pnl(side: str, entry: float, exit_: float, volume: float) -> float:
    """Realized P&L: longs profit on a rise, shorts on a fall."""
    direction = 1.0 if side == "long" else -1.0
    return round(direction * (exit_ - entry) * volume, 2)


@router.post("", response_model=TradeOut)
def open_trade(payload: TradeOpen) -> TradeOut:
    if payload.side not in ("long", "short"):
        raise HTTPException(400, "side must be 'long' or 'short'")
    session = PgSession()
    try:
        trade = Trade(
            symbol=payload.symbol.upper(),
            interval=payload.interval,
            side=payload.side,
            status="open",
            entry_ts=payload.entry_ts,
            entry_price=payload.entry_price,
            volume=payload.volume,
            stop=payload.stop,
            entry_version_id=version_at_ts(
                session, payload.symbol.upper(), payload.interval, payload.entry_ts
            ),
            notes=payload.notes,
        )
        session.add(trade)
        session.commit()
        session.refresh(trade)
        return TradeOut.model_validate(trade)
    finally:
        session.close()


@router.post("/{trade_id}/close", response_model=TradeOut)
def close_trade(trade_id: int, payload: TradeClose) -> TradeOut:
    session = PgSession()
    try:
        trade = session.get(Trade, trade_id)
        if trade is None:
            raise HTTPException(404, f"trade not found: {trade_id}")
        if trade.status == "closed":
            raise HTTPException(409, "trade is already closed")
        trade.exit_ts = payload.exit_ts
        trade.exit_price = payload.exit_price
        trade.exit_version_id = version_at_ts(
            session, trade.symbol, trade.interval, payload.exit_ts
        )
        trade.pnl = _pnl(
            trade.side, trade.entry_price, payload.exit_price, trade.volume
        )
        trade.status = "closed"
        if payload.notes:
            trade.notes = payload.notes
        session.commit()
        session.refresh(trade)
        return TradeOut.model_validate(trade)
    finally:
        session.close()


@router.get("", response_model=list[TradeOut])
def list_trades(
    symbol: str | None = None, interval: str | None = None
) -> list[TradeOut]:
    session = PgSession()
    try:
        q = session.query(Trade)
        if symbol:
            q = q.filter(Trade.symbol == symbol.upper())
        if interval:
            q = q.filter(Trade.interval == interval)
        rows = q.order_by(Trade.entry_ts.desc()).all()
        return [TradeOut.model_validate(t) for t in rows]
    finally:
        session.close()


@router.get("/{trade_id}", response_model=TradeOut)
def get_trade(trade_id: int) -> TradeOut:
    session = PgSession()
    try:
        trade = session.get(Trade, trade_id)
        if trade is None:
            raise HTTPException(404, f"trade not found: {trade_id}")
        return TradeOut.model_validate(trade)
    finally:
        session.close()


@router.post("/{trade_id}/analyze")
async def analyze(trade_id: int) -> dict:
    """LLM (or deterministic) read of the glyph conditions around a trade."""
    session = PgSession()
    try:
        trade = session.get(Trade, trade_id)
        if trade is None:
            raise HTTPException(404, f"trade not found: {trade_id}")
        return await analyze_trade(session, trade)
    finally:
        session.close()


@router.delete("/{trade_id}")
def delete_trade(trade_id: int) -> dict[str, int]:
    session = PgSession()
    try:
        trade = session.get(Trade, trade_id)
        if trade is None:
            raise HTTPException(404, f"trade not found: {trade_id}")
        session.delete(trade)
        session.commit()
        return {"deleted": trade_id}
    finally:
        session.close()
