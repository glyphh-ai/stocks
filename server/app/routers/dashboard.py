"""Read endpoints that drive the dashboard chart.

GET /symbols              -> configured stocks (symbol/interval) with spans
GET /paths                -> selectable node paths for a symbol/interval
GET /series               -> one time series per requested path + metric
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..db import PgSession
from ..models import Trade
from ..storage import (
    baseline_drift,
    delete_history,
    drift_series,
    list_paths,
    list_symbols,
    value_series,
)

router = APIRouter(tags=["dashboard"])

Metric = Literal["baseline", "delta", "value"]


class SymbolInfo(BaseModel):
    symbol: str
    interval: str
    versions: int
    first_ts: datetime | None
    last_ts: datetime | None


class PathInfo(BaseModel):
    level: str
    path: str


class Point(BaseModel):
    t: datetime
    v: float | None


class Series(BaseModel):
    path: str
    metric: Metric
    points: list[Point]


class SeriesResponse(BaseModel):
    symbol: str
    interval: str
    metric: Metric
    series: list[Series]


@router.get("/symbols", response_model=list[SymbolInfo])
def symbols() -> list[SymbolInfo]:
    session = PgSession()
    try:
        return [SymbolInfo(**row) for row in list_symbols(session)]
    finally:
        session.close()


@router.get("/paths", response_model=list[PathInfo])
def paths(symbol: str, interval: str = "1m") -> list[PathInfo]:
    session = PgSession()
    try:
        return [PathInfo(**row) for row in list_paths(session, symbol, interval)]
    finally:
        session.close()


def _fetch(session, symbol: str, interval: str, path: str, metric: Metric) -> list[Point]:
    if metric == "value":
        rows = value_series(session, symbol, interval, path)
    elif metric == "delta":
        rows = drift_series(session, symbol, interval, path)
    else:
        rows = baseline_drift(session, symbol, interval, path)
    return [Point(t=ts, v=val) for ts, val in rows]


class ClearResult(BaseModel):
    symbol: str
    interval: str
    versions_removed: int
    trades_removed: int


@router.delete("/history", response_model=ClearResult)
def clear_history(
    symbol: str, interval: str, remove_trades: bool = False
) -> ClearResult:
    """Wipe all glyph history for a symbol/interval. Trades are preserved
    unless remove_trades is set."""
    session = PgSession()
    try:
        versions = delete_history(session, symbol, interval)
        trades = 0
        if remove_trades:
            trades = (
                session.query(Trade)
                .filter(Trade.symbol == symbol, Trade.interval == interval)
                .delete(synchronize_session=False)
            )
        session.commit()
        return ClearResult(
            symbol=symbol,
            interval=interval,
            versions_removed=versions,
            trades_removed=int(trades),
        )
    finally:
        session.close()


@router.get("/series", response_model=SeriesResponse)
def series(
    symbol: str,
    interval: str = "1m",
    metric: Metric = "baseline",
    path: list[str] = Query(default=["cortex"]),
) -> SeriesResponse:
    session = PgSession()
    try:
        out = [
            Series(path=p, metric=metric, points=_fetch(session, symbol, interval, p, metric))
            for p in path
        ]
        return SeriesResponse(symbol=symbol, interval=interval, metric=metric, series=out)
    finally:
        session.close()
