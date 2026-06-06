"""Persist and query temporal glyphs.

write_glyph()      -> encode an instance and store version + all node vectors
drift_series()     -> consecutive-version drift over time at one path (in DB)
drift_between()    -> drift between two specific versions at one path
baseline_drift()   -> drift of every version vs the first, at one path
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from .hdc import drift, encode_glyph
from .models import GlyphNode, GlyphPrediction, GlyphVersion


def write_glyph(
    session: Session,
    symbol: str,
    interval: str,
    ts: datetime,
    glyph_json: dict,
) -> int:
    """Encode a filled glyph instance and persist version + every node vector."""
    _, nodes = encode_glyph(glyph_json)
    version = GlyphVersion(
        symbol=symbol,
        interval=interval,
        ts=ts,
        model=glyph_json.get("model", ""),
        glyph=glyph_json,
    )
    for key, vec in nodes.items():
        level = key.split(":", 1)[0]
        version.nodes.append(GlyphNode(level=level, path=key, vec=vec.tolist()))
    session.add(version)
    session.commit()
    return version.id


def version_at_ts(
    session: Session, symbol: str, interval: str, ts: datetime
) -> int | None:
    """The glyph version whose timestamp is nearest to `ts` for symbol/interval.

    Used to pin a trade leg to the HDC snapshot that best represents market
    conditions at the moment of the trade. Returns None if no versions exist.
    """
    row = session.execute(
        text(
            """
            SELECT id FROM glyph_version
            WHERE symbol = :symbol AND interval = :interval
            ORDER BY ABS(EXTRACT(EPOCH FROM (ts - :ts))) ASC
            LIMIT 1
            """
        ),
        {"symbol": symbol, "interval": interval, "ts": ts},
    ).first()
    return int(row.id) if row else None


def drift_series(
    session: Session, symbol: str, interval: str, path: str = "cortex"
) -> list[tuple[datetime, float | None]]:
    """Drift between each version and the previous one, ordered by time.

    The first row's drift is None (no predecessor). Computed in-DB with the
    pgvector cosine-distance operator over a window.
    """
    sql = text(
        """
        SELECT ts, dist FROM (
            SELECT gv.ts AS ts,
                   gn.vec <=> LAG(gn.vec) OVER (ORDER BY gv.ts) AS dist
            FROM glyph_version gv
            JOIN glyph_node gn ON gn.version_id = gv.id
            WHERE gv.symbol = :symbol AND gv.interval = :interval AND gn.path = :path
        ) s
        ORDER BY ts
        """
    )
    rows = session.execute(sql, {"symbol": symbol, "interval": interval, "path": path})
    return [(r.ts, None if r.dist is None else float(r.dist)) for r in rows]


def baseline_drift(
    session: Session, symbol: str, interval: str, path: str = "cortex"
) -> list[tuple[datetime, float]]:
    """Drift of every version vs the earliest version, at one path."""
    sql = text(
        """
        WITH series AS (
            SELECT gv.ts AS ts, gn.vec AS vec
            FROM glyph_version gv
            JOIN glyph_node gn ON gn.version_id = gv.id
            WHERE gv.symbol = :symbol AND gv.interval = :interval AND gn.path = :path
            ORDER BY gv.ts
        ),
        base AS (SELECT vec FROM series LIMIT 1)
        SELECT series.ts AS ts, series.vec <=> base.vec AS dist
        FROM series, base
        ORDER BY series.ts
        """
    )
    rows = session.execute(sql, {"symbol": symbol, "interval": interval, "path": path})
    return [(r.ts, float(r.dist)) for r in rows]


def drift_between(
    session: Session, version_a: int, version_b: int, path: str = "cortex"
) -> float:
    """Drift between two specific versions at one path."""
    a = session.scalar(
        select(GlyphNode.vec).where(
            GlyphNode.version_id == version_a, GlyphNode.path == path
        )
    )
    b = session.scalar(
        select(GlyphNode.vec).where(
            GlyphNode.version_id == version_b, GlyphNode.path == path
        )
    )
    return drift(np.asarray(a, dtype=np.float32), np.asarray(b, dtype=np.float32))


def list_symbols(session: Session) -> list[dict]:
    """Every (symbol, interval) that has versions, with counts and time span."""
    sql = text(
        """
        SELECT symbol, interval, COUNT(*) AS versions,
               MIN(ts) AS first_ts, MAX(ts) AS last_ts
        FROM glyph_version
        GROUP BY symbol, interval
        ORDER BY symbol, interval
        """
    )
    return [
        {
            "symbol": r.symbol,
            "interval": r.interval,
            "versions": int(r.versions),
            "first_ts": r.first_ts,
            "last_ts": r.last_ts,
        }
        for r in session.execute(sql)
    ]


def delete_history(session: Session, symbol: str, interval: str) -> int:
    """Delete every glyph version (cascading its nodes) for a symbol/interval.

    The glyph_node FK has ON DELETE CASCADE, so the nodes go with the versions.
    Trades are untouched — they reference versions softly and are cleared
    separately when the caller opts in. Returns the version count removed."""
    result = session.execute(
        text(
            "DELETE FROM glyph_version "
            "WHERE symbol = :symbol AND interval = :interval"
        ),
        {"symbol": symbol, "interval": interval},
    )
    return int(result.rowcount or 0)


def list_paths(session: Session, symbol: str, interval: str) -> list[dict]:
    """Distinct node paths for a symbol/interval (from its latest version)."""
    sql = text(
        """
        SELECT gn.level AS level, gn.path AS path
        FROM glyph_node gn
        JOIN glyph_version gv ON gv.id = gn.version_id
        WHERE gv.id = (
            SELECT id FROM glyph_version
            WHERE symbol = :symbol AND interval = :interval
            ORDER BY ts DESC LIMIT 1
        )
        ORDER BY gn.path
        """
    )
    rows = session.execute(sql, {"symbol": symbol, "interval": interval})
    return [{"level": r.level, "path": r.path} for r in rows]


def value_series(
    session: Session, symbol: str, interval: str, role_path: str
) -> list[tuple[datetime, float | None]]:
    """Raw scalar value of a role across versions, read from the glyph JSON.

    role_path is "role:<layer>/<segment>/<role>". Returns (ts, value) per
    version; value is None where the role had no numeric value.
    """
    _, body = role_path.split(":", 1) if ":" in role_path else ("role", role_path)
    layer_key, segment_key, role_key = body.split("/")
    sql = text(
        """
        SELECT ts, glyph FROM glyph_version
        WHERE symbol = :symbol AND interval = :interval
        ORDER BY ts
        """
    )
    out: list[tuple[datetime, float | None]] = []
    for r in session.execute(sql, {"symbol": symbol, "interval": interval}):
        out.append((r.ts, _extract_role_value(r.glyph, layer_key, segment_key, role_key)))
    return out


def _latest_prediction_glyph(
    session: Session, symbol: str, interval: str
) -> dict | None:
    """The predicted glyph to derive the green tree from (prefer the ahead row)."""
    row = (
        session.query(GlyphPrediction)
        .filter(
            GlyphPrediction.symbol == symbol,
            GlyphPrediction.interval == interval,
        )
        .order_by(
            (GlyphPrediction.horizon == "ahead").desc(),
            GlyphPrediction.target_ts.desc(),
        )
        .first()
    )
    return row.glyph if row else None


def prediction_paths(session: Session, symbol: str, interval: str) -> list[dict]:
    """Green-tree node paths for the predicted glyph: cortex, layers, segments,
    and scalar *signal* roles only (symbol roles aren't predicted)."""
    glyph = _latest_prediction_glyph(session, symbol, interval)
    if not glyph:
        return []
    out: list[dict] = [{"level": "cortex", "path": "cortex"}]
    for layer in glyph.get("layers", []):
        lk = layer.get("key")
        out.append({"level": "layer", "path": f"layer:{lk}"})
        for seg in layer.get("segments", []):
            sk = seg.get("key")
            out.append({"level": "segment", "path": f"segment:{lk}/{sk}"})
            for role in seg.get("roles", []):
                if role.get("type", "symbol") != "scalar":
                    continue
                out.append(
                    {"level": "role", "path": f"role:{lk}/{sk}/{role.get('key')}"}
                )
    return out


def prediction_value_series(
    session: Session, symbol: str, interval: str, role_path: str
) -> list[tuple[datetime, float | None, str]]:
    """Predicted scalar value of a signal across the stored predictions, ordered
    by the interval being predicted — the history walk-forward plus the single
    one-step-ahead point. Each tuple carries its horizon ('history' | 'ahead')
    so the caller can render the ahead step distinctly. role_path is
    'role:<layer>/<segment>/<role>'."""
    _, body = role_path.split(":", 1) if ":" in role_path else ("role", role_path)
    layer_key, segment_key, role_key = body.split("/")
    rows = (
        session.query(GlyphPrediction)
        .filter(
            GlyphPrediction.symbol == symbol,
            GlyphPrediction.interval == interval,
        )
        .order_by(GlyphPrediction.target_ts)
        .all()
    )
    return [
        (
            r.target_ts,
            _extract_role_value(r.glyph, layer_key, segment_key, role_key),
            r.horizon,
        )
        for r in rows
    ]


def latest_prediction(
    session: Session, symbol: str, interval: str
) -> GlyphPrediction | None:
    """The one-step-ahead projection row, if any."""
    return (
        session.query(GlyphPrediction)
        .filter(
            GlyphPrediction.symbol == symbol,
            GlyphPrediction.interval == interval,
            GlyphPrediction.horizon == "ahead",
        )
        .order_by(GlyphPrediction.target_ts.desc())
        .first()
    )


def _extract_role_value(
    glyph: dict, layer_key: str, segment_key: str, role_key: str
) -> float | None:
    for layer in glyph.get("layers", []):
        if layer.get("key") != layer_key:
            continue
        for seg in layer.get("segments", []):
            if seg.get("key") != segment_key:
                continue
            for role in seg.get("roles", []):
                if role.get("key") == role_key:
                    val = role.get("value")
                    try:
                        return float(val)
                    except (TypeError, ValueError):
                        return None
    return None
