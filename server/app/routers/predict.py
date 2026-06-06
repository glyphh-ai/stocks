"""Project the next glyph from recorded history.

GET  /predict                 -> top-N projected next glyphs (real-time beam)
GET  /predict/backtest        -> walk-forward predicted-vs-actual price series
POST /predict/backtest/analyze -> LLM critique of the beam's backtest accuracy

The /predict/next family is the persisted ensemble predictor (beam +
autoregressive + trades + LLM): a green prediction glyph stored per interval.

POST /predict/next/refresh    -> rebuild the stored prediction set (history + ahead)
GET  /predict/next            -> the one-step-ahead projection (glyph + breakdown)
GET  /predict/next/paths      -> green-tree node paths for the predicted glyph
GET  /predict/next/series     -> predicted signal value series (history + ahead)
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..backtest import analyze_backtest, run_backtest
from ..db import PgSession
from ..predict import predict_next_glyph
from ..predictor import refresh_predictions
from ..storage import (
    latest_prediction,
    prediction_paths,
    prediction_value_series,
)

router = APIRouter(prefix="/predict", tags=["predict"])


@router.get("")
def predict(
    symbol: str,
    interval: str = "1d",
    beam_width: int = 8,
    top_n: int = 3,
) -> dict:
    session = PgSession()
    try:
        return predict_next_glyph(
            session,
            symbol.upper(),
            interval,
            beam_width=beam_width,
            top_n=top_n,
        )
    finally:
        session.close()


@router.get("/backtest")
def backtest(
    symbol: str,
    interval: str = "1d",
    warmup: int = 10,
    beam_width: int = 8,
) -> dict:
    """Walk-forward: at each interval predict the next price from prior history."""
    session = PgSession()
    try:
        return run_backtest(
            session, symbol.upper(), interval, warmup=warmup, beam_width=beam_width
        )
    finally:
        session.close()


@router.post("/backtest/analyze")
async def backtest_analyze(
    symbol: str,
    interval: str = "1d",
    warmup: int = 10,
    beam_width: int = 8,
) -> dict:
    """LLM read on how the beam is performing and how to improve it."""
    session = PgSession()
    try:
        return await analyze_backtest(
            session, symbol.upper(), interval, warmup=warmup, beam_width=beam_width
        )
    finally:
        session.close()


class PathInfo(BaseModel):
    level: str
    path: str


class Point(BaseModel):
    t: datetime
    v: float | None


class PredictionSeries(BaseModel):
    path: str
    points: list[Point]  # walk-forward history projections
    ahead: Point | None = None  # the single one-step-ahead projection


class PredictionSeriesResponse(BaseModel):
    symbol: str
    interval: str
    series: list[PredictionSeries]


@router.post("/next/refresh")
async def next_refresh(
    symbol: str, interval: str = "1d", with_llm: bool = True
) -> dict:
    """Rebuild the stored ensemble predictions (walk-forward history + ahead)."""
    session = PgSession()
    try:
        return await refresh_predictions(
            session, symbol.upper(), interval, with_llm=with_llm
        )
    finally:
        session.close()


@router.get("/next")
def next_prediction(symbol: str, interval: str = "1d") -> dict:
    """The one-step-ahead projection: predicted glyph, per-signal breakdown,
    confidence, and the interval it targets. Null if none is stored yet."""
    session = PgSession()
    try:
        row = latest_prediction(session, symbol.upper(), interval)
        if row is None:
            return {"symbol": symbol.upper(), "interval": interval, "prediction": None}
        return {
            "symbol": row.symbol,
            "interval": row.interval,
            "prediction": {
                "target_ts": row.target_ts,
                "basis_versions": row.basis_versions,
                "confidence": row.confidence,
                "components": row.components,
                "glyph": row.glyph,
            },
        }
    finally:
        session.close()


@router.get("/next/paths", response_model=list[PathInfo])
def next_paths(symbol: str, interval: str = "1d") -> list[PathInfo]:
    session = PgSession()
    try:
        return [
            PathInfo(**row)
            for row in prediction_paths(session, symbol.upper(), interval)
        ]
    finally:
        session.close()


@router.get("/next/series", response_model=PredictionSeriesResponse)
def next_series(
    symbol: str,
    interval: str = "1d",
    path: list[str] = Query(default=[]),
) -> PredictionSeriesResponse:
    """Predicted signal value series (history walk-forward + ahead point)."""
    session = PgSession()
    try:
        sym = symbol.upper()
        out: list[PredictionSeries] = []
        for p in path:
            rows = prediction_value_series(session, sym, interval, p)
            history_pts = [
                Point(t=ts, v=v) for ts, v, h in rows if h != "ahead"
            ]
            ahead = next(
                (Point(t=ts, v=v) for ts, v, h in rows if h == "ahead"), None
            )
            out.append(PredictionSeries(path=p, points=history_pts, ahead=ahead))
        return PredictionSeriesResponse(symbol=sym, interval=interval, series=out)
    finally:
        session.close()
