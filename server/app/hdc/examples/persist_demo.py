"""End-to-end persistence check against a live pgvector.

Writes a few temporal versions of AAPL (price drifts up; news rank dips on the
last one) then reads drift back out of Postgres at several levels.

Prereq:  docker compose up -d pgvector  &&  ./.venv/bin/python -m app.migrate
Run from server/:  ./.venv/bin/python -m app.hdc.examples.persist_demo
"""

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import PgSession
from app.models import GlyphNode, GlyphVersion
from app.storage import baseline_drift, drift_series, write_glyph


def fill(template: dict, values: dict) -> dict:
    g = copy.deepcopy(template)
    for layer in g["layers"]:
        for seg in layer["segments"]:
            for role in seg["roles"]:
                role["value"] = values[role["key"]]
    return g


def main() -> None:
    template = json.loads(
        (Path(__file__).parent / "equity.template.json").read_text()
    )
    base = {
        "price": 196.0, "volume": 1_200_000, "interval": "1m",
        "vs_sp500_pct": 0.4, "sector_volume": 5_000_000,
        "gold": 2_300, "silver": 29, "bitcoin": 68_000,
        "yahoo_rank": 7, "fed_tone": 6,
    }
    t0 = datetime(2026, 6, 5, 14, 30, tzinfo=timezone.utc)
    steps = [
        base,
        {**base, "price": 196.6},
        {**base, "price": 197.4},
        {**base, "price": 197.9, "yahoo_rank": 4},  # bad news on the last tick
    ]

    session = PgSession()
    try:
        # Clean prior run so the demo is repeatable.
        ids = [
            v for (v,) in session.query(GlyphVersion.id)
            .filter_by(symbol="AAPL", interval="1m").all()
        ]
        if ids:
            session.query(GlyphNode).filter(GlyphNode.version_id.in_(ids)).delete(
                synchronize_session=False
            )
            session.query(GlyphVersion).filter(GlyphVersion.id.in_(ids)).delete(
                synchronize_session=False
            )
            session.commit()

        for i, vals in enumerate(steps):
            write_glyph(session, "AAPL", "1m", t0 + timedelta(minutes=i), fill(template, vals))

        for path in [
            "cortex",
            "role:symbol/price_action/price",
            "role:macro/news_sentiment/yahoo_rank",
        ]:
            print(f"\nconsecutive drift  [{path}]")
            for ts, d in drift_series(session, "AAPL", "1m", path):
                print(f"  {ts:%H:%M}  {'-' if d is None else f'{d:.4f}'}")

        print("\nbaseline drift vs first version  [cortex]")
        for ts, d in baseline_drift(session, "AAPL", "1m", "cortex"):
            print(f"  {ts:%H:%M}  {d:.4f}")
    finally:
        session.close()


if __name__ == "__main__":
    main()
