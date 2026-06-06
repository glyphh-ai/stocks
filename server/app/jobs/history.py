"""Fetch historical OHLCV bars from Yahoo's chart API (no API key).

Used to seed the DB with real, time-varying price history for a symbol so the
glyph drift series reflects actual market movement rather than a constant stub.
"""

from __future__ import annotations

import json
import time as _time
import urllib.parse
import urllib.request
from bisect import bisect_right
from datetime import datetime, timezone

_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/"

# A wide history window per interval, so a point-in-time lookup for any
# reasonable replay timestamp is covered by one cached fetch. Intraday tokens
# are bounded by what Yahoo will serve for that granularity.
_RANGE_FOR = {
    "1m": "7d",
    "2m": "60d",
    "5m": "60d",
    "15m": "60d",
    "30m": "60d",
    "1h": "2y",
    "1d": "5y",
    "1wk": "10y",
    "1mo": "max",
}

# Memoize whole-range fetches so a 120-bar replay that calls tools per tick
# (each needing gold/spx/etc. as-of that tick) hits Yahoo once per series, not
# once per tick. Keyed by (symbol, range, interval); short TTL so a live tick
# still sees a fresh-enough tail.
_SERIES_CACHE: dict[tuple[str, str, str], tuple[float, list[dict]]] = {}
_CACHE_TTL = 300.0  # seconds


def _range_for(interval: str) -> str:
    return _RANGE_FOR.get(interval, "5y")


def fetch_series_cached(symbol: str, interval: str = "1d") -> list[dict]:
    """OHLC bars for a symbol over a wide window, memoized with a short TTL."""
    range_ = _range_for(interval)
    key = (symbol.upper(), range_, interval)
    now = _time.time()
    hit = _SERIES_CACHE.get(key)
    if hit and now - hit[0] < _CACHE_TTL:
        return hit[1]
    bars = fetch_ohlc(symbol, range_, interval)
    _SERIES_CACHE[key] = (now, bars)
    return bars


def series_upto(
    symbol: str, ts: datetime | None = None, *, interval: str = "1d"
) -> list[dict]:
    """Bars at or before `ts` (oldest first). `ts=None` returns the full series.

    This is the point-in-time primitive: callers never see a bar dated after
    `ts`, so engineered features and as-of reads carry no lookahead.
    """
    bars = fetch_series_cached(symbol, interval)
    if ts is None:
        return bars
    times = [b["ts"] for b in bars]
    return bars[: bisect_right(times, ts)]


def as_of(
    symbol: str, ts: datetime | None = None, *, field: str = "close", interval: str = "1d"
) -> float | None:
    """The most recent value of `field` at or before `ts` (latest if ts=None)."""
    bars = series_upto(symbol, ts, interval=interval)
    if not bars:
        return None
    return bars[-1].get(field)


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
