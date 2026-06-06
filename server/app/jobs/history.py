"""Fetch historical OHLCV bars from Yahoo's chart API (no API key).

Used to seed the DB with real, time-varying price history for a symbol so the
glyph drift series reflects actual market movement rather than a constant stub.
"""

from __future__ import annotations

import json
import urllib.parse
import urllib.request
from datetime import datetime, timezone

_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"


def fetch_ohlc(symbol: str, range_: str = "6mo", interval: str = "1d") -> list[dict]:
    """Return a list of {ts, close, volume} bars, oldest first.

    range_ / interval are Yahoo's own tokens (e.g. range 1mo/6mo/1y/5y,
    interval 1d/1wk/1mo, or intraday 1m/5m/1h over short ranges). Bars whose
    close is null (holidays, gaps) are dropped.
    """
    url = (
        _CHART
        + urllib.parse.quote(symbol)
        + f"?range={urllib.parse.quote(range_)}&interval={urllib.parse.quote(interval)}"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
        data = json.loads(resp.read())

    result = (data.get("chart", {}).get("result") or [None])[0]
    if not result:
        return []
    stamps = result.get("timestamp") or []
    quote = (result.get("indicators", {}).get("quote") or [{}])[0]
    closes = quote.get("close") or []
    volumes = quote.get("volume") or []

    bars: list[dict] = []
    for i, t in enumerate(stamps):
        close = closes[i] if i < len(closes) else None
        if close is None:
            continue
        vol = volumes[i] if i < len(volumes) else None
        bars.append(
            {
                "ts": datetime.fromtimestamp(t, tz=timezone.utc),
                "close": float(close),
                "volume": float(vol) if vol is not None else 0.0,
            }
        )
    return bars


def fetch_quote(symbol: str) -> dict:
    """Return the latest live quote {symbol, price, prev_close, currency, ts}.

    Reads Yahoo's chart meta (regularMarketPrice), which updates intraday with
    no API key. Raises ValueError if the symbol has no quote.
    """
    url = _CHART + urllib.parse.quote(symbol) + "?range=1d&interval=1m"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:  # noqa: S310
        data = json.loads(resp.read())

    result = (data.get("chart", {}).get("result") or [None])[0]
    meta = (result or {}).get("meta") or {}
    price = meta.get("regularMarketPrice")
    if price is None:
        raise ValueError(f"no quote for {symbol!r}")
    ts = meta.get("regularMarketTime")
    return {
        "symbol": meta.get("symbol", symbol.upper()),
        "price": float(price),
        "prev_close": (
            float(meta["chartPreviousClose"])
            if meta.get("chartPreviousClose") is not None
            else None
        ),
        "currency": meta.get("currency", "USD"),
        "ts": (
            datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
            if ts is not None
            else None
        ),
    }
