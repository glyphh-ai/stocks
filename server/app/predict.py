"""Beam-search projection of the next glyph from recorded history.

Each scalar role traces a value series across versions. We model its
per-step dynamics (a Gaussian over historical deltas) and search the joint
space of next-role-values with a beam, scoring candidates on two terms:

  - dynamics:   how typical each role's proposed step is, given its history
  - coherence:  how close the joint state sits to a real historical state
                (a non-separable term — it couples roles, which is what makes
                the beam meaningful rather than a per-role argmax)

The surviving beams are the projected next glyphs. Each is re-encoded so we
can report its projected cortex drift from the latest recorded glyph.
"""

from __future__ import annotations

import copy
import math
from datetime import datetime

import numpy as np
from sqlalchemy import text
from sqlalchemy.orm import Session

from .hdc import drift as _drift, encode_glyph

# A role identified by its path within the glyph, with its numeric history.
_TWO_PI_LOG = math.log(2.0 * math.pi)


def _history(session: Session, symbol: str, interval: str) -> list[dict]:
    """Recorded glyph JSON instances for symbol/interval, oldest first."""
    rows = session.execute(
        text(
            """
            SELECT glyph, ts FROM glyph_version
            WHERE symbol = :symbol AND interval = :interval
            ORDER BY ts ASC
            """
        ),
        {"symbol": symbol, "interval": interval},
    )
    return [{"glyph": r.glyph, "ts": r.ts} for r in rows]


def _scalar_roles(glyph: dict) -> list[tuple[str, tuple[float, float]]]:
    """Ordered (path, range) for every scalar role in a glyph template."""
    out: list[tuple[str, tuple[float, float]]] = []
    for layer in glyph.get("layers", []):
        for seg in layer.get("segments", []):
            for role in seg.get("roles", []):
                if role.get("type", "symbol") != "scalar":
                    continue
                path = f"{layer['key']}/{seg['key']}/{role['key']}"
                lo, hi = role.get("range", [0.0, 1.0])
                out.append((path, (float(lo), float(hi))))
    return out


def _role_value(glyph: dict, path: str) -> float | None:
    layer_key, seg_key, role_key = path.split("/")
    for layer in glyph.get("layers", []):
        if layer.get("key") != layer_key:
            continue
        for seg in layer.get("segments", []):
            if seg.get("key") != seg_key:
                continue
            for role in seg.get("roles", []):
                if role.get("key") == role_key:
                    try:
                        return float(role.get("value"))
                    except (TypeError, ValueError):
                        return None
    return None


def _set_role_value(glyph: dict, path: str, value: float) -> None:
    layer_key, seg_key, role_key = path.split("/")
    for layer in glyph.get("layers", []):
        if layer.get("key") != layer_key:
            continue
        for seg in layer.get("segments", []):
            if seg.get("key") != seg_key:
                continue
            for role in seg.get("roles", []):
                if role.get("key") == role_key:
                    role["value"] = value
                    return


def _gaussian_logpdf(x: float, mu: float, sigma: float) -> float:
    z = (x - mu) / sigma
    return -0.5 * z * z - math.log(sigma) - 0.5 * _TWO_PI_LOG


def predict_next_glyph(
    session: Session,
    symbol: str,
    interval: str,
    beam_width: int = 8,
    top_n: int = 3,
    candidates_per_role: int = 3,
    coherence_weight: float = 1.5,
) -> dict:
    """Project the next glyph from all recorded history via beam search."""
    history = _history(session, symbol, interval)
    return _predict_core(
        history,
        symbol,
        interval,
        beam_width=beam_width,
        top_n=top_n,
        candidates_per_role=candidates_per_role,
        coherence_weight=coherence_weight,
    )


def _predict_core(
    history: list[dict],
    symbol: str,
    interval: str,
    *,
    beam_width: int = 8,
    top_n: int = 3,
    candidates_per_role: int = 3,
    coherence_weight: float = 1.5,
    with_drift: bool = True,
) -> dict:
    """Beam-search the next glyph from a history slice.

    When with_drift is False the projected glyphs are not re-encoded — that
    skips the HD vectorization per candidate, which matters when this runs
    hundreds of times in a walk-forward backtest. projected_drift is then None.
    """
    latest = history[-1]["glyph"] if history else None

    if latest is None or len(history) < 2:
        return {
            "symbol": symbol,
            "interval": interval,
            "basis_versions": len(history),
            "latest_ts": history[-1]["ts"] if history else None,
            "modeled_roles": 0,
            "predictions": [],
            "note": "Need at least two recorded glyphs to model dynamics.",
        }

    roles = _scalar_roles(latest)

    # Per-role series across versions (None where missing), plus delta stats.
    series: dict[str, list[float | None]] = {p: [] for p, _ in roles}
    for h in history:
        for path, _ in roles:
            series[path].append(_role_value(h["glyph"], path))

    modeled: list[str] = []
    last: dict[str, float] = {}
    mu: dict[str, float] = {}
    sigma: dict[str, float] = {}
    ranges: dict[str, tuple[float, float]] = {}
    cand: dict[str, list[float]] = {}

    for path, rng in roles:
        vals = [v for v in series[path] if v is not None]
        if len(vals) < 2:
            continue
        arr = np.asarray(vals, dtype=np.float64)
        deltas = np.diff(arr)
        lo, hi = rng
        span = max(hi - lo, 1e-9)
        m = float(deltas.mean())
        s = float(deltas.std())
        s = max(s, span * 1e-3)  # floor so constant roles stay well-defined

        last_v = float(arr[-1])
        offsets = np.linspace(-1.0, 1.0, candidates_per_role)
        values = sorted({
            float(np.clip(last_v + m + o * s, lo, hi)) for o in offsets
        })

        modeled.append(path)
        last[path] = last_v
        mu[path] = m
        sigma[path] = s
        ranges[path] = rng
        cand[path] = values

    if not modeled:
        return {
            "symbol": symbol,
            "interval": interval,
            "basis_versions": len(history),
            "latest_ts": history[-1]["ts"],
            "modeled_roles": 0,
            "predictions": [],
            "note": "No scalar role has enough numeric history to model.",
        }

    # Standardized historical state matrix (rows=versions, cols=modeled roles)
    # for the coherence term. NaN where a role was missing in that version.
    n = len(history)
    H = np.full((n, len(modeled)), np.nan, dtype=np.float64)
    for j, path in enumerate(modeled):
        col = np.asarray(
            [np.nan if v is None else v for v in series[path]], dtype=np.float64
        )
        H[:, j] = col
    col_mean = np.nanmean(H, axis=0)
    col_std = np.nanstd(H, axis=0)
    col_std[col_std < 1e-9] = 1.0
    Hs = (H - col_mean) / col_std

    def coherence(assign: dict[str, float], upto: int) -> float:
        idx = list(range(upto))
        a = np.array(
            [(assign[modeled[j]] - col_mean[j]) / col_std[j] for j in idx]
        )
        sub = Hs[:, idx]
        diff = sub - a
        d2 = np.nanmean(diff * diff, axis=1)
        d2 = d2[~np.isnan(d2)]
        if d2.size == 0:
            return 0.0
        return -coherence_weight * float(np.sqrt(d2.min()))

    # Beam search: expand role by role, keep the top beam_width partials.
    Beam = list[tuple[dict[str, float], float]]
    beam: Beam = [({}, 0.0)]
    for step, path in enumerate(modeled, start=1):
        expanded: Beam = []
        for assign, _ in beam:
            for v in cand[path]:
                a2 = dict(assign)
                a2[path] = v
                dyn = sum(
                    _gaussian_logpdf(a2[p] - last[p], mu[p], sigma[p])
                    for p in a2
                )
                expanded.append((a2, dyn + coherence(a2, step)))
        expanded.sort(key=lambda x: x[1], reverse=True)
        beam = expanded[:beam_width]

    top = beam[:top_n]
    scores = np.array([s for _, s in top], dtype=np.float64)
    # Softmax over scores → a relative confidence per surviving beam.
    shifted = scores - scores.max()
    weights = np.exp(shifted)
    conf = weights / weights.sum()

    latest_cortex = encode_glyph(latest)[1]["cortex"] if with_drift else None

    predictions = []
    for rank, ((assign, score), c) in enumerate(zip(top, conf), start=1):
        proj_drift: float | None = None
        if with_drift:
            projected = copy.deepcopy(latest)
            for path, v in assign.items():
                _set_role_value(projected, path, v)
            proj_drift = _drift(latest_cortex, encode_glyph(projected)[1]["cortex"])

        role_moves = {}
        for path, v in assign.items():
            role_moves[path] = {
                "from": round(last[path], 6),
                "to": round(v, 6),
                "delta": round(v - last[path], 6),
            }
        predictions.append(
            {
                "rank": rank,
                "score": round(float(score), 4),
                "confidence": round(float(c), 4),
                "projected_drift": (
                    round(float(proj_drift), 4) if proj_drift is not None else None
                ),
                "roles": role_moves,
            }
        )

    # Headline movers from the rank-1 projection (largest range-normalized step).
    movers = []
    if predictions:
        for path, mv in predictions[0]["roles"].items():
            lo, hi = ranges[path]
            span = max(hi - lo, 1e-9)
            movers.append((abs(mv["delta"]) / span, path, mv))
        movers.sort(key=lambda x: x[0], reverse=True)
    top_movers = [
        {"role": p, **mv, "intensity": round(i, 4)} for i, p, mv in movers[:5]
    ]

    return {
        "symbol": symbol,
        "interval": interval,
        "basis_versions": len(history),
        "latest_ts": history[-1]["ts"],
        "modeled_roles": len(modeled),
        "predictions": predictions,
        "top_movers": top_movers,
        "note": None,
    }
