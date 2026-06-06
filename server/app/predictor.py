"""Ensemble projection of the next-interval glyph.

The beam search is one voice among several. For each scalar *signal* role we
blend four sources into a projected next value:

  - autoregressive: the signal's own momentum (EWMA of its recent deltas)
  - beam:           the rank-1 value the coupled beam search projects
  - trades:         a directional nudge learned from how the signal sat at the
                    entry of winning vs losing trades
  - llm:            an optional per-signal bias from Claude, given the recent
                    trajectory, the beam projection, and the trade record

The blended values fill a copy of the latest glyph — the projected next glyph,
stored as a GlyphPrediction. Walk-forward 'history' rows predict each past
interval from prior history only (autoregressive + beam, so there is no
lookahead); the single 'ahead' row projects the next, not-yet-printed interval
with the full ensemble. Both are persisted so the predicted signal lines (and
the one-step-ahead point) can be charted against the actuals.

This is deliberately about *signals* (scalar roles), not symbol roles — symbol
roles are copied through unchanged.
"""

from __future__ import annotations

import copy
import math
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from .config import settings
from .models import GlyphPrediction, GlyphVersion, Trade
from .predict import (
    _history,
    _predict_core,
    _role_value,
    _scalar_roles,
    _set_role_value,
)

EWMA_ALPHA = 0.4  # weight on the most recent delta in the momentum term
W_AR = 1.0  # autoregressive weight in the base blend
W_BEAM = 1.0  # beam weight in the base blend
TRADE_NUDGE = 0.5  # scale of the trade-bias nudge (in units of signal volatility)
LLM_NUDGE = 1.5  # scale of the LLM-bias nudge (in units of signal volatility)
DEFAULT_WARMUP = 5


def _ewma_next(values: list[float | None], alpha: float) -> float | None:
    """Next value from an EWMA of the series' deltas (momentum extrapolation)."""
    vals = [v for v in values if v is not None]
    if len(vals) < 2:
        return None
    deltas = np.diff(np.asarray(vals, dtype=np.float64))
    e = float(deltas[0])
    for d in deltas[1:]:
        e = alpha * float(d) + (1.0 - alpha) * e
    return float(vals[-1]) + e


def _predict_signals(
    history: list[dict],
    symbol: str,
    interval: str,
    *,
    trade_bias: dict[str, float] | None = None,
    llm_bias: dict[str, float] | None = None,
    llm_confidence: float | None = None,
) -> tuple[dict[str, float], dict[str, Any], float]:
    """Blend the ensemble sources into a value per scalar signal.

    Returns (assignments, per-signal components, overall confidence).
    """
    latest = history[-1]["glyph"]
    roles = _scalar_roles(latest)

    series: dict[str, list[float | None]] = {
        p: [_role_value(h["glyph"], p) for h in history] for p, _ in roles
    }

    beam = _predict_core(history, symbol, interval, top_n=1, with_drift=False)
    beam_vals: dict[str, float] = {}
    if beam.get("predictions"):
        for path, mv in beam["predictions"][0]["roles"].items():
            beam_vals[path] = float(mv["to"])

    assign: dict[str, float] = {}
    comp: dict[str, Any] = {}
    agreements: list[float] = []

    for path, (lo, hi) in roles:
        vals = [v for v in series[path] if v is not None]
        if len(vals) < 2:
            continue
        span = max(hi - lo, 1e-9)
        last = float(vals[-1])

        ar = _ewma_next(series[path], EWMA_ALPHA)
        bm = beam_vals.get(path)

        pts: list[float] = []
        ws: list[float] = []
        if ar is not None:
            pts.append(ar)
            ws.append(W_AR)
        if bm is not None:
            pts.append(bm)
            ws.append(W_BEAM)
        base = float(np.average(pts, weights=ws)) if pts else last

        std = float(np.std(np.diff(np.asarray(vals, dtype=np.float64))))
        std = max(std, span * 1e-3)

        t_nudge = TRADE_NUDGE * trade_bias[path] * std if (trade_bias and path in trade_bias) else 0.0
        l_nudge = LLM_NUDGE * float(llm_bias[path]) * std if (llm_bias and path in llm_bias) else 0.0

        final = float(np.clip(base + t_nudge + l_nudge, lo, hi))
        assign[path] = final
        comp[path] = {
            "autoregressive": round(ar, 6) if ar is not None else None,
            "beam": round(bm, 6) if bm is not None else None,
            "trades": round(t_nudge, 6),
            "llm": round(l_nudge, 6),
            "from": round(last, 6),
            "final": round(final, 6),
            "delta": round(final - last, 6),
        }
        if ar is not None and bm is not None:
            agreements.append(math.exp(-3.0 * abs(ar - bm) / span))

    conf = float(np.mean(agreements)) if agreements else 0.0
    if llm_confidence is not None:
        conf = 0.5 * conf + 0.5 * float(llm_confidence)
    return assign, comp, round(conf, 4)


def _projected_glyph(latest: dict, assign: dict[str, float]) -> dict:
    g = copy.deepcopy(latest)
    for path, v in assign.items():
        _set_role_value(g, path, v)
    return g


def _trade_bias(
    session: Session, symbol: str, interval: str, history: list[dict]
) -> dict[str, float]:
    """Per-signal directional prior from closed trades.

    For each closed trade we look at how each signal sat (z-scored over history)
    at the trade's entry, and credit it +/- by whether the trade made money.
    A positive bias means high readings of that signal preceded winners, so the
    predictor nudges it up. Needs at least two closed, P&L-resolved trades.
    """
    closed = [
        t
        for t in session.query(Trade)
        .filter(
            Trade.symbol == symbol,
            Trade.interval == interval,
            Trade.status == "closed",
        )
        .all()
        if t.net_pnl is not None and t.entry_version_id
    ]
    if len(closed) < 2:
        return {}

    roles = _scalar_roles(history[-1]["glyph"])
    stats: dict[str, tuple[float, float]] = {}
    for path, _ in roles:
        vals = [v for v in (_role_value(h["glyph"], path) for h in history) if v is not None]
        if len(vals) >= 2:
            stats[path] = (float(np.mean(vals)), max(float(np.std(vals)), 1e-9))

    acc: dict[str, float] = {p: 0.0 for p in stats}
    cnt: dict[str, int] = {p: 0 for p in stats}
    for t in closed:
        ev = session.get(GlyphVersion, t.entry_version_id)
        if not ev:
            continue
        outcome = 1.0 if t.net_pnl > 0 else -1.0
        for path, (mean, std) in stats.items():
            v = _role_value(ev.glyph, path)
            if v is None:
                continue
            acc[path] += outcome * (v - mean) / std
            cnt[path] += 1

    return {
        p: float(np.clip(acc[p] / cnt[p], -1.0, 1.0))
        for p in stats
        if cnt[p] > 0
    }


def _median_step(history: list[dict]) -> timedelta:
    ts = [h["ts"] for h in history]
    gaps = [
        (ts[i] - ts[i - 1]).total_seconds()
        for i in range(1, len(ts))
        if ts[i] and ts[i - 1]
    ]
    secs = float(np.median(gaps)) if gaps else 86400.0
    return timedelta(seconds=max(secs, 1.0))


def _build_history_rows(
    history: list[dict], symbol: str, interval: str, warmup: int
) -> list[dict]:
    """Walk-forward: predict each past interval from prior history only."""
    rows: list[dict] = []
    n = len(history)
    for i in range(max(warmup, 2), n):
        assign, comp, conf = _predict_signals(history[:i], symbol, interval)
        if not assign:
            continue
        rows.append(
            {
                "target_ts": history[i]["ts"],
                "horizon": "history",
                "basis_versions": i,
                "glyph": _projected_glyph(history[i - 1]["glyph"], assign),
                "components": comp,
                "confidence": conf,
            }
        )
    return rows


async def refresh_predictions(
    session: Session,
    symbol: str,
    interval: str,
    *,
    warmup: int = DEFAULT_WARMUP,
    with_llm: bool = True,
) -> dict[str, Any]:
    """Rebuild the full prediction set (history walk-forward + one-step-ahead).

    Predictions are derived, so this wipes the symbol/interval's existing rows
    and reinserts. Returns counts and the ahead projection's summary.
    """
    history = _history(session, symbol, interval)
    base = {"symbol": symbol, "interval": interval, "history_rows": 0, "ahead": None}
    if len(history) < warmup + 1:
        return {**base, "note": f"Need at least {warmup + 1} recorded glyphs."}

    session.query(GlyphPrediction).filter(
        GlyphPrediction.symbol == symbol, GlyphPrediction.interval == interval
    ).delete(synchronize_session=False)

    rows = _build_history_rows(history, symbol, interval, warmup)

    # One-step-ahead with the full ensemble.
    trade_bias = _trade_bias(session, symbol, interval, history)
    beam = _predict_core(history, symbol, interval, top_n=1, with_drift=False)
    beam_vals = (
        {p: float(mv["to"]) for p, mv in beam["predictions"][0]["roles"].items()}
        if beam.get("predictions")
        else {}
    )

    llm_bias: dict[str, float] = {}
    llm_conf: float | None = None
    llm_raw: dict[str, Any] | None = None
    if with_llm:
        from .forecaster import llm_forecast

        llm_bias, llm_conf, llm_raw = await llm_forecast(
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
    ahead_summary = None
    if assign:
        target_ts = history[-1]["ts"] + _median_step(history)
        rows.append(
            {
                "target_ts": target_ts,
                "horizon": "ahead",
                "basis_versions": len(history),
                "glyph": _projected_glyph(history[-1]["glyph"], assign),
                "components": comp,
                "confidence": conf,
            }
        )
        ahead_summary = {
            "target_ts": target_ts,
            "confidence": conf,
            "components": comp,
            "trade_bias": trade_bias or None,
            "llm": llm_raw,
        }

    for r in rows:
        session.add(
            GlyphPrediction(symbol=symbol, interval=interval, **r)
        )
    session.commit()

    return {
        **base,
        "history_rows": sum(1 for r in rows if r["horizon"] == "history"),
        "ahead": ahead_summary,
        "llm_available": bool(settings.anthropic_api_key),
        "note": None,
    }
