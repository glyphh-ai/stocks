"""Offline end-to-end job run: deterministic tools + a stub LLM executor.

Proves the orchestrator fills roles from tool/llm steps (sequential 'symbol'
layer, parallel 'macro' layer), persists a version, and that a worse news
verdict shows up as drift on the news role and the cortex.

Prereq:  docker compose up -d pgvector  &&  ./.venv/bin/python -m app.migrate
Run from server/:  ./.venv/bin/python -m app.jobs.demo
"""

import asyncio
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.db import PgSession
from app.jobs import StubLLMExecutor, register, run_glyph
from app.models import GlyphNode, GlyphVersion
from app.storage import drift_series

TEMPLATE = (
    Path(__file__).resolve().parent.parent / "hdc" / "examples" / "equity.template.json"
)


def register_demo_tools() -> None:
    register("quote", lambda symbol: {"price": 197.0, "volume": 1_200_000})
    register("market_rel", lambda symbol: {"vs_sp500_pct": 0.4, "sector_volume": 5_000_000})
    register("commodity_prices", lambda: {"gold": 2300, "silver": 29, "bitcoin": 68000})
    register("yahoo_news", lambda symbol: [f"{symbol} demo headline"])


async def main() -> None:
    template = json.loads(TEMPLATE.read_text())
    register_demo_tools()

    t0 = datetime(2026, 6, 5, 15, 0, tzinfo=timezone.utc)
    runs = [
        ("good news", {"verdict": {"score": 8}, "fed": {"score": 6}}),
        ("bad news", {"verdict": {"score": 3}, "fed": {"score": 6}}),
    ]

    session = PgSession()
    try:
        ids = [v for (v,) in session.query(GlyphVersion.id).filter_by(symbol="DEMO", interval="1m")]
        if ids:
            session.query(GlyphNode).filter(GlyphNode.version_id.in_(ids)).delete(synchronize_session=False)
            session.query(GlyphVersion).filter(GlyphVersion.id.in_(ids)).delete(synchronize_session=False)
            session.commit()

        for i, (label, canned) in enumerate(runs):
            vid, filled = await run_glyph(
                template, "DEMO", "1m", t0 + timedelta(minutes=i),
                StubLLMExecutor(canned), session,
            )
            news = next(
                r for layer in filled["layers"] for seg in layer["segments"]
                for r in seg["roles"] if r["key"] == "yahoo_rank"
            )
            print(f"{label:9s} -> version {vid}  yahoo_rank={news['value']}  price={_role(filled,'price')}")

        print("\ndrift good->bad:")
        for path in ["cortex", "role:macro/news_sentiment/yahoo_rank", "role:symbol/price_action/price"]:
            series = drift_series(session, "DEMO", "1m", path)
            d = series[-1][1]
            print(f"  {path:42s} {d:.4f}")
    finally:
        session.close()


def _role(filled: dict, key: str):
    for layer in filled["layers"]:
        for seg in layer["segments"]:
            for r in seg["roles"]:
                if r["key"] == key:
                    return r.get("value")
    return None


if __name__ == "__main__":
    asyncio.run(main())
