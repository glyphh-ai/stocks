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
from .models import GlyphNode, GlyphVersion


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
