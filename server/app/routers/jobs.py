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
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..db import PgSession
from ..forecaster import reset_conversation
from ..jobs import default_executor, run_glyph
from ..jobs.history import fetch_ohlc, fetch_quote
from ..jobs.runner import run_segment
from ..models import GlyphNode, GlyphPrediction, GlyphVersion
from ..predict import _predict_core
from ..predictor import (
    DEFAULT_WARMUP,
    _median_step,
    _predict_signals,
    _projected_glyph,
    _trade_bias,
)
from ..storage import delete_history, write_glyph

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
        raise HTTPException(400, f"no historical data for {req.symbol!r} — check the ticker")

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


class ReplayRequest(BaseModel):
    symbol: str
    range: str = "6mo"
    interval: str = "1d"
    template: dict[str, Any] | None = None
    template_name: str = "equity.template.json"
    warmup: int = DEFAULT_WARMUP
    remove_trades: bool = False
    with_llm_ahead: bool = True


def _reset_all(session: Any, symbol: str, interval: str, remove_trades: bool) -> int:
    """Wipe every derived artifact for symbol/interval so a replay starts clean."""
    from ..models import Trade

    versions = delete_history(session, symbol, interval)
    session.query(GlyphPrediction).filter(
        GlyphPrediction.symbol == symbol, GlyphPrediction.interval == interval
    ).delete(synchronize_session=False)
    reset_conversation(session, symbol, interval)
    if remove_trades:
        session.query(Trade).filter(
            Trade.symbol == symbol, Trade.interval == interval
        ).delete(synchronize_session=False)
    session.commit()
    return versions


def _sse(event: str, **data: Any) -> str:
    return f"data: {json.dumps({'event': event, **data})}\n\n"


@router.post("/replay")
async def replay(req: ReplayRequest) -> StreamingResponse:
    """Reset all data, then walk history bar-by-bar: for each historic tick run
    the FULL config glyph pipeline point-in-time (every tool/llm step, as-of that
    bar's timestamp) and immediately build the walk-forward prediction for that
    bar from the history accumulated so far. A final one-step-ahead row uses the
    full ensemble (trade + LLM bias). Progress streams as SSE so the chart builds
    tick by tick rather than refreshing on page load.
    """
    template = _load_template(req)  # type: ignore[arg-type]
    bars = fetch_ohlc(req.symbol, req.range, req.interval)
    if not bars:
        raise HTTPException(400, f"no historical data for {req.symbol!r} — check the ticker")

    symbol, interval, warmup = req.symbol, req.interval, max(req.warmup, 2)
    executor = default_executor()

    async def stream() -> Any:
        session = PgSession()
        try:
            removed = _reset_all(session, symbol, interval, req.remove_trades)
            yield _sse("reset", versions_removed=removed, bars=len(bars))

            history: list[dict] = []
            pred_rows = 0
            for i, bar in enumerate(bars):
                ts = bar["ts"]
                try:
                    version_id, filled = await run_glyph(
                        template, symbol, interval, ts, executor, session
                    )
                except Exception as exc:  # noqa: BLE001 - one bad bar shouldn't abort
                    yield _sse("error", index=i, ts=ts.isoformat(), detail=f"{type(exc).__name__}: {exc}")
                    continue

                history.append({"glyph": filled, "ts": ts})
                yield _sse(
                    "bar",
                    index=i,
                    total=len(bars),
                    ts=ts.isoformat(),
                    version_id=version_id,
                )

                # Walk-forward: predict the bar we just added from prior history.
                if len(history) > warmup:
                    prior = history[:-1]
                    assign, comp, conf = _predict_signals(prior, symbol, interval)
                    if assign:
                        session.add(
                            GlyphPrediction(
                                symbol=symbol,
                                interval=interval,
                                target_ts=ts,
                                horizon="history",
                                basis_versions=len(prior),
                                glyph=_projected_glyph(prior[-1]["glyph"], assign),
                                components=comp,
                                confidence=conf,
                            )
                        )
                        session.commit()
                        pred_rows += 1
                        yield _sse(
                            "prediction",
                            target_ts=ts.isoformat(),
                            confidence=conf,
                            rows=pred_rows,
                        )

            ahead = await _build_ahead(session, symbol, interval, history, req.with_llm_ahead)
            if ahead is not None:
                yield _sse("ahead", **ahead)
            yield _sse("done", versions=len(history), history_rows=pred_rows)
        finally:
            session.close()

    return StreamingResponse(stream(), media_type="text/event-stream")


async def _build_ahead(
    session: Any,
    symbol: str,
    interval: str,
    history: list[dict],
    with_llm: bool,
) -> dict[str, Any] | None:
    """Persist the one-step-ahead prediction with the full ensemble; return a summary."""
    if len(history) < 2:
        return None
    trade_bias = _trade_bias(session, symbol, interval, history)
    beam = _predict_core(history, symbol, interval, top_n=1, with_drift=False)
    beam_vals = (
        {p: float(mv["to"]) for p, mv in beam["predictions"][0]["roles"].items()}
        if beam.get("predictions")
        else {}
    )

    llm_bias: dict[str, float] = {}
    llm_conf: float | None = None
    if with_llm:
        from ..forecaster import llm_forecast

        llm_bias, llm_conf, _ = await llm_forecast(
            session, symbol, interval, history, beam_vals, trade_bias
        )

    assign, comp, conf = _predict_signals(
        history,
        symbol,
        interval,
        trade_bias=trade_bias,
        llm_bias=llm_bias,
        llm_confidence=llm_conf,
    )
    if not assign:
        return None
    target_ts = history[-1]["ts"] + _median_step(history)
    session.add(
        GlyphPrediction(
            symbol=symbol,
            interval=interval,
            target_ts=target_ts,
            horizon="ahead",
            basis_versions=len(history),
            glyph=_projected_glyph(history[-1]["glyph"], assign),
            components=comp,
            confidence=conf,
        )
    )
    session.commit()
    return {"target_ts": target_ts.isoformat(), "confidence": conf}
