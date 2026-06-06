"""Project the next glyph from recorded history via beam search.

GET  /predict                 -> top-N projected next glyphs (real-time)
GET  /predict/backtest        -> walk-forward predicted-vs-actual price series
POST /predict/backtest/analyze -> LLM critique of the beam's backtest accuracy
"""

from __future__ import annotations

from fastapi import APIRouter

from ..backtest import analyze_backtest, run_backtest
from ..db import PgSession
from ..predict import predict_next_glyph

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
