"""Trigger a glyph job run: fetch via tools, judge via the LLM, persist a version.

POST /jobs/run runs every layer's segment jobs against `symbol`/`interval`, fills
the template, and writes a new temporal glyph. The executor is real Claude when
ANTHROPIC_API_KEY is set, otherwise a stub that refuses `llm` steps — so a run
with news_sentiment needs a key, but a tool-only template works offline.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import PgSession
from ..jobs import default_executor, run_glyph
from ..jobs.history import fetch_ohlc, fetch_quote
from ..jobs.runner import run_segment
from ..models import GlyphNode, GlyphVersion
from ..storage import write_glyph

router = APIRouter(prefix="/jobs", tags=["jobs"])

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "hdc" / "examples"


class RunRequest(BaseModel):
    symbol: str
    interval: str = "1m"
    ts: datetime | None = None
    template: dict[str, Any] | None = None
    template_name: str = "equity.template.json"


class RunResponse(BaseModel):
    version_id: int
    symbol: str
    interval: str
    ts: datetime
    roles: dict[str, Any] = Field(default_factory=dict)


def _load_template(req: RunRequest) -> dict[str, Any]:
    if req.template is not None:
        return req.template
    path = _TEMPLATE_DIR / req.template_name
    if not path.is_file():
        raise HTTPException(404, f"template not found: {req.template_name}")
    return json.loads(path.read_text())


def _flatten_roles(filled: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for layer in filled.get("layers", []):
        for seg in layer.get("segments", []):
            for role in seg.get("roles", []):
                if "value" in role:
                    out[f"{layer['key']}/{seg['key']}/{role['key']}"] = role["value"]
    return out


class TestSegmentRequest(BaseModel):
    symbol: str = "TEST"
    interval: str = "1m"
    segment: dict[str, Any]


class TestSegmentResponse(BaseModel):
    roles: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


@router.post("/test-segment", response_model=TestSegmentResponse)
async def test_segment(req: TestSegmentRequest) -> TestSegmentResponse:
    """Run a single segment's job in isolation and return the role values it sets.

    Drives the config UI's test panel — no glyph is persisted. Uses the real
    Claude executor when a key is set, else the stub (which refuses llm steps).
    """
    base_ctx = {"symbol": req.symbol, "interval": req.interval}
    try:
        roles = await run_segment(req.segment, base_ctx, default_executor())
        return TestSegmentResponse(roles=roles)
    except Exception as exc:  # noqa: BLE001 - surface the failure to the UI
        return TestSegmentResponse(error=f"{type(exc).__name__}: {exc}")


class BackfillRequest(BaseModel):
    symbol: str
    range: str = "6mo"
    interval: str = "1d"
    template: dict[str, Any] | None = None
    template_name: str = "equity.template.json"
    replace: bool = True


class BackfillResponse(BaseModel):
    symbol: str
    interval: str
    written: int
    first_ts: datetime | None = None
    last_ts: datetime | None = None


def _role_default(role: dict[str, Any]) -> float:
    """A stable midpoint value for a scalar role we have no real data for."""
    lo, hi = role.get("range") or [0.0, 1.0]
    return (float(lo) + float(hi)) / 2.0


def _fill_bar(
    template: dict[str, Any],
    symbol: str,
    interval: str,
    bar: dict[str, Any],
    prev_close: float | None,
    spx_return_pct: float,
) -> dict[str, Any]:
    """Fill a template from one price bar.

    Roles we can derive from real data (price/volume/market-relative) get live
    values; everything else gets a constant midpoint so it contributes no
    artificial drift over the backfilled window.
    """
    derived: dict[str, float] = {
        "price": bar["close"],
        "volume": bar["volume"],
        "sector_volume": bar["volume"],
    }
    if prev_close:
        sym_return_pct = (bar["close"] / prev_close - 1) * 100
        derived["vs_sp500_pct"] = sym_return_pct - spx_return_pct

    g = copy.deepcopy(template)
    g["symbol"] = symbol
    g["interval"] = interval
    for layer in g.get("layers", []):
        for seg in layer.get("segments", []):
            for role in seg.get("roles", []):
                key = role["key"]
                if role.get("type") == "symbol":
                    role["value"] = interval if key == "interval" else symbol
                elif key in derived:
                    role["value"] = derived[key]
                else:
                    role["value"] = _role_default(role)
    return g


def _clear_versions(session: Any, symbol: str, interval: str) -> None:
    ids = [
        v
        for (v,) in session.query(GlyphVersion.id)
        .filter_by(symbol=symbol, interval=interval)
        .all()
    ]
    if not ids:
        return
    session.query(GlyphNode).filter(GlyphNode.version_id.in_(ids)).delete(
        synchronize_session=False
    )
    session.query(GlyphVersion).filter(GlyphVersion.id.in_(ids)).delete(
        synchronize_session=False
    )
    session.commit()


@router.post("/backfill", response_model=BackfillResponse)
def backfill(req: BackfillRequest) -> BackfillResponse:
    """Seed the DB with one glyph version per historical bar for a symbol.

    Pulls real OHLCV from Yahoo (no key) plus ^GSPC for the market-relative
    signal. News/macro roles stay at a neutral constant — there's no historical
    headline data offline, so backfilling them would invent drift.
    """
    template = _load_template(req)  # type: ignore[arg-type]
    bars = fetch_ohlc(req.symbol, req.range, req.interval)
    if not bars:
        raise HTTPException(502, f"no historical data for {req.symbol!r}")

    spx_close = {b["ts"]: b["close"] for b in fetch_ohlc("^GSPC", req.range, req.interval)}

    session = PgSession()
    try:
        if req.replace:
            _clear_versions(session, req.symbol, req.interval)

        written = 0
        prev_close: float | None = None
        prev_spx: float | None = None
        for bar in bars:
            spx_return_pct = 0.0
            cur_spx = spx_close.get(bar["ts"])
            if prev_spx and cur_spx:
                spx_return_pct = (cur_spx / prev_spx - 1) * 100
            filled = _fill_bar(
                template, req.symbol, req.interval, bar, prev_close, spx_return_pct
            )
            write_glyph(session, req.symbol, req.interval, bar["ts"], filled)
            written += 1
            prev_close = bar["close"]
            if cur_spx:
                prev_spx = cur_spx
    finally:
        session.close()

    return BackfillResponse(
        symbol=req.symbol,
        interval=req.interval,
        written=written,
        first_ts=bars[0]["ts"],
        last_ts=bars[-1]["ts"],
    )


class QuoteResponse(BaseModel):
    symbol: str
    price: float
    prev_close: float | None = None
    currency: str = "USD"
    ts: str | None = None


@router.get("/quote", response_model=QuoteResponse)
def quote(symbol: str) -> QuoteResponse:
    """Live market quote for a symbol (Yahoo, no key). Drives the trade modal."""
    try:
        return QuoteResponse(**fetch_quote(symbol))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    except Exception as exc:  # noqa: BLE001 - upstream/network failure
        raise HTTPException(502, f"quote fetch failed: {exc}") from exc


@router.post("/run", response_model=RunResponse)
async def run(req: RunRequest) -> RunResponse:
    template = _load_template(req)
    ts = req.ts or datetime.now(timezone.utc)
    executor = default_executor()

    session = PgSession()
    try:
        version_id, filled = await run_glyph(
            template, req.symbol, req.interval, ts, executor, session
        )
    finally:
        session.close()

    return RunResponse(
        version_id=version_id,
        symbol=req.symbol,
        interval=req.interval,
        ts=ts,
        roles=_flatten_roles(filled),
    )
