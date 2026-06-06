"""Walk-forward evaluation of the beam-search price prediction.

For each interval in a symbol's recorded history (after a warmup window), we
re-run the beam search using only the glyphs that existed up to that point and
read off the rank-1 projected price. Comparing that projection to the price
that actually printed at the next interval — across the whole chart — tells us
whether the beam has any predictive signal.

The headline metric is directional accuracy: of all the steps, how often did
the projected move (up/down vs the prior close) match reality. That is the
number to push past 60%. We also report magnitude error (MAE/MAPE/RMSE) and a
skill score against a naive persistence baseline (tomorrow == today).
"""

from __future__ import annotations

import json
import math
from typing import Any

from sqlalchemy.orm import Session

from .config import settings
from .predict import _history, _predict_core, _role_value, _scalar_roles


def _price_path(glyph: dict) -> str | None:
    """The scalar role that carries price (role key 'price')."""
    for path, _ in _scalar_roles(glyph):
        if path.split("/")[-1] == "price":
            return path
    return None


def _sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def _metrics(points: list[dict]) -> dict[str, Any] | None:
    if not points:
        return None
    n = len(points)
    abs_err = [abs(p["predicted"] - p["actual"]) for p in points]
    naive_err = [abs(p["actual"] - p["prev"]) for p in points]
    pct_err = [
        abs(p["predicted"] - p["actual"]) / abs(p["actual"])
        for p in points
        if p["actual"] != 0
    ]
    sq_err = [(p["predicted"] - p["actual"]) ** 2 for p in points]

    directional = [
        _sign(p["predicted"] - p["prev"]) == _sign(p["actual"] - p["prev"])
        for p in points
        if _sign(p["actual"] - p["prev"]) != 0
    ]
    correct = sum(1 for d in directional if d)
    mae = sum(abs_err) / n
    naive_mae = sum(naive_err) / n

    return {
        "n": n,
        "directional_accuracy": (
            round(100.0 * correct / len(directional), 2) if directional else None
        ),
        "directional_n": len(directional),
        "mae": round(mae, 4),
        "mape": round(100.0 * sum(pct_err) / len(pct_err), 3) if pct_err else None,
        "rmse": round(math.sqrt(sum(sq_err) / n), 4),
        "naive_mae": round(naive_mae, 4),
        "skill_vs_naive": (
            round(1.0 - mae / naive_mae, 4) if naive_mae > 0 else None
        ),
        "mean_confidence": round(sum(p["confidence"] for p in points) / n, 4),
    }


def run_backtest(
    session: Session,
    symbol: str,
    interval: str,
    warmup: int = 10,
    beam_width: int = 8,
    candidates_per_role: int = 3,
    coherence_weight: float = 1.5,
) -> dict[str, Any]:
    """Walk every interval after `warmup`, predicting the next price each step."""
    history = _history(session, symbol, interval)
    n = len(history)
    base = {
        "symbol": symbol,
        "interval": interval,
        "basis_versions": n,
        "warmup": warmup,
        "points": [],
        "metrics": None,
    }
    if n < warmup + 2:
        return {**base, "note": f"Need at least {warmup + 2} recorded glyphs."}

    price_path = _price_path(history[-1]["glyph"])
    if price_path is None:
        return {**base, "note": "No scalar 'price' role to evaluate."}

    points: list[dict] = []
    for i in range(warmup, n):
        res = _predict_core(
            history[:i],
            symbol,
            interval,
            beam_width=beam_width,
            top_n=1,
            candidates_per_role=candidates_per_role,
            coherence_weight=coherence_weight,
            with_drift=False,
        )
        preds = res.get("predictions") or []
        if not preds or price_path not in preds[0]["roles"]:
            continue
        prev = _role_value(history[i - 1]["glyph"], price_path)
        actual = _role_value(history[i]["glyph"], price_path)
        if prev is None or actual is None:
            continue
        points.append(
            {
                "ts": history[i]["ts"],
                "prev": round(prev, 4),
                "predicted": round(float(preds[0]["roles"][price_path]["to"]), 4),
                "actual": round(actual, 4),
                "confidence": preds[0]["confidence"],
            }
        )

    return {
        **base,
        "price_path": price_path,
        "points": points,
        "metrics": _metrics(points),
        "note": None,
    }


_SYSTEM = (
    "You are an ML/quant reviewer evaluating a price-prediction backtest. The "
    "predictor is a beam search over a hyperdimensional 'glyph': each scalar "
    "role (price, volume, market-relative signals, etc.) traces a value series "
    "across daily snapshots. The beam models each role's per-step change as a "
    "Gaussian over its historical deltas (the 'dynamics' term) and scores joint "
    "candidate states by how close they sit to the nearest real historical "
    "state (a non-separable 'coherence' term). The rank-1 beam's projected "
    "price is the prediction. You are given walk-forward metrics and a sample "
    "of the worst misses. Judge whether the beam shows real directional signal "
    "(beating 50% and the naive persistence baseline) and give concrete, "
    "specific changes to push directional accuracy past 60%. Be technical and "
    "do not give financial advice."
)

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "assessment": {"type": "string"},
        "beam_strengths": {"type": "array", "items": {"type": "string"}},
        "beam_weaknesses": {"type": "array", "items": {"type": "string"}},
        "improvements": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "idea": {"type": "string"},
                    "rationale": {"type": "string"},
                    "expected_impact": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                    },
                },
                "required": ["idea", "rationale", "expected_impact"],
                "additionalProperties": False,
            },
        },
        "verdict": {
            "type": "string",
            "enum": ["signal", "inconclusive", "no_signal"],
        },
    },
    "required": [
        "assessment",
        "beam_strengths",
        "beam_weaknesses",
        "improvements",
        "verdict",
    ],
    "additionalProperties": False,
}


def _worst_misses(points: list[dict], k: int = 8) -> list[dict]:
    ranked = sorted(
        points, key=lambda p: abs(p["predicted"] - p["actual"]), reverse=True
    )
    return [
        {
            "ts": str(p["ts"]),
            "prev": p["prev"],
            "predicted": p["predicted"],
            "actual": p["actual"],
            "confidence": p["confidence"],
        }
        for p in ranked[:k]
    ]


def _deterministic_assessment(metrics: dict[str, Any]) -> dict[str, Any]:
    da = metrics.get("directional_accuracy")
    skill = metrics.get("skill_vs_naive")
    if da is None:
        verdict = "inconclusive"
    elif da >= 60:
        verdict = "signal"
    elif da <= 50:
        verdict = "no_signal"
    else:
        verdict = "inconclusive"
    return {
        "assessment": (
            f"Directional accuracy {da}% over {metrics.get('directional_n')} "
            f"scored steps; skill vs naive {skill}. "
            "Set ANTHROPIC_API_KEY for a full LLM critique."
        ),
        "beam_strengths": [],
        "beam_weaknesses": [],
        "improvements": [],
        "verdict": verdict,
    }


async def analyze_backtest(
    session: Session,
    symbol: str,
    interval: str,
    warmup: int = 10,
    beam_width: int = 8,
) -> dict[str, Any]:
    """Run the backtest and hand its metrics to Claude for a beam critique."""
    bt = run_backtest(
        session, symbol, interval, warmup=warmup, beam_width=beam_width
    )
    metrics = bt.get("metrics")
    if not metrics:
        return {
            "backtest": {k: bt[k] for k in ("symbol", "interval", "metrics", "note")},
            "llm_available": False,
            "analysis": {
                "assessment": bt.get("note") or "Not enough history to backtest.",
                "beam_strengths": [],
                "beam_weaknesses": [],
                "improvements": [],
                "verdict": "inconclusive",
            },
        }

    summary = {
        "symbol": symbol,
        "interval": interval,
        "basis_versions": bt["basis_versions"],
        "warmup": warmup,
        "metrics": metrics,
        "worst_misses": _worst_misses(bt["points"]),
    }

    if not settings.anthropic_api_key:
        return {
            "backtest": {"symbol": symbol, "interval": interval, "metrics": metrics},
            "llm_available": False,
            "analysis": _deterministic_assessment(metrics),
        }

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=2000,
        thinking={"type": "disabled"},
        system=[{"type": "text", "text": _SYSTEM}],
        messages=[
            {
                "role": "user",
                "content": "Evaluate this beam-search backtest:\n"
                + json.dumps(summary, default=str),
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return {
        "backtest": {"symbol": symbol, "interval": interval, "metrics": metrics},
        "llm_available": True,
        "analysis": json.loads(text),
    }
