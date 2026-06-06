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
LLM_NUDGE = 0.7  # scale of the LLM-bias nudge (in units of signal volatility)
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


_LLM_SYSTEM = (
    "You are a quantitative signal forecaster. You are given, for one symbol, "
    "the recent trajectories of normalized market signals (scalar roles of a "
    "hyperdimensional 'glyph'), the beam-search projection for the next "
    "interval, and a short record of recent trades. For each signal you have a "
    "view on, output a directional bias in [-1, 1] (negative = expect the "
    "signal to fall next interval, positive = rise, 0 = no view) and a "
    "confidence in [0, 1]. Be conservative: only nudge signals where the "
    "trajectory or trade record genuinely supports a direction. Do not give "
    "financial advice."
)

_LLM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "signals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "bias": {"type": "number"},
                    "confidence": {"type": "number"},
                },
                "required": ["path", "bias", "confidence"],
                "additionalProperties": False,
            },
        },
        "rationale": {"type": "string"},
        "overall_confidence": {"type": "number"},
    },
    "required": ["signals", "rationale", "overall_confidence"],
    "additionalProperties": False,
}


async def _llm_bias(
    symbol: str,
    interval: str,
    history: list[dict],
    beam_vals: dict[str, float],
    trade_bias: dict[str, float],
) -> tuple[dict[str, float], float | None, dict[str, Any] | None]:
    """Ask Claude for a per-signal directional bias. No key -> empty (skipped)."""
    if not settings.anthropic_api_key:
        return {}, None, None

    roles = _scalar_roles(history[-1]["glyph"])
    tail = history[-12:]
    trajectories: dict[str, list[float | None]] = {
        path: [_role_value(h["glyph"], path) for h in tail] for path, _ in roles
    }
    summary = {
        "symbol": symbol,
        "interval": interval,
        "recent_trajectories": {
            p: [round(v, 4) if v is not None else None for v in vs]
            for p, vs in trajectories.items()
        },
        "beam_projection": {p: round(v, 4) for p, v in beam_vals.items()},
        "trade_bias": {p: round(v, 4) for p, v in trade_bias.items()},
    }

    from anthropic import AsyncAnthropic
    import json

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1500,
        thinking={"type": "disabled"},
        system=[{"type": "text", "text": _LLM_SYSTEM}],
        messages=[
            {
                "role": "user",
                "content": "Forecast next-interval signal biases:\n"
                + json.dumps(summary, default=str),
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": _LLM_SCHEMA}},
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    data = json.loads(text)

    valid = {p for p, _ in roles}
    bias = {
        s["path"]: float(np.clip(s["bias"], -1.0, 1.0))
        for s in data.get("signals", [])
        if s.get("path") in valid
    }
    overall = data.get("overall_confidence")
    return bias, (float(overall) if overall is not None else None), data


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
        llm_bias, llm_conf, llm_raw = await _llm_bias(
            symbol, interval, history, beam_vals, trade_bias
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
