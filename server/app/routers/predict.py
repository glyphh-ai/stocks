"""Project the next glyph from recorded history via beam search.

GET /predict?symbol=&interval= -> top-N projected next glyphs, each with the
per-role moves and the projected cortex drift from the latest recorded glyph.
"""

from __future__ import annotations

from fastapi import APIRouter

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
