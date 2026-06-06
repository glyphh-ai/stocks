"""Registry of deterministic tool functions that job steps can call by name.

These are the ".py wrappers": pure-ish, no LLM. Register with @tool("name", ...)
and declare metadata (params, outputs, credential kind) so the config UI can
offer the tool in a dropdown and render the right inputs. Adding a new data
source = adding one @tool here; the builder needs no changes beyond the creds.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from typing import Any, Callable

_REGISTRY: dict[str, Callable] = {}
_SPECS: dict[str, dict[str, Any]] = {}


def _unit(*parts: object) -> float:
    """Deterministic 0..1 value seeded by the given parts (no randomness)."""
    h = hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def tool(
    name: str,
    *,
    description: str = "",
    params: list[dict[str, Any]] | None = None,
    outputs: list[str] | None = None,
    cred_kind: str = "none",
    config: list[dict[str, Any]] | None = None,
) -> Callable[[Callable], Callable]:
    """Register a tool and its UI metadata.

    params:    runtime call args (e.g. {"name":"symbol","type":"symbol"}).
    outputs:   keys the tool returns, so the UI can map them onto roles.
    cred_kind: none | bearer | basic | header — which credential it accepts.
    config:    non-secret per-step config (e.g. a url).
    """

    def deco(fn: Callable) -> Callable:
        _REGISTRY[name] = fn
        _SPECS[name] = {
            "name": name,
            "description": description or (fn.__doc__ or "").strip().split("\n")[0],
            "params": params or [],
            "outputs": outputs or [],
            "cred_kind": cred_kind,
            "config": config or [],
        }
        return fn

    return deco


def register(name: str, fn: Callable) -> None:
    """Imperative register/override (used by demos and tests)."""
    _REGISTRY[name] = fn


def get_tool(name: str) -> Callable:
    if name not in _REGISTRY:
        raise KeyError(f"no tool registered as {name!r}")
    return _REGISTRY[name]


def list_tool_specs() -> list[dict[str, Any]]:
    """All registered tools' metadata, for the config UI's tool palette."""
    return [_SPECS[k] for k in sorted(_SPECS)]


@tool(
    "yahoo_news",
    description="Recent Yahoo Finance headlines for a symbol (no key).",
    params=[{"name": "symbol", "type": "symbol", "required": True}],
    outputs=["(list of headlines)"],
)
def yahoo_news(symbol: str, limit: int = 8) -> list[str]:
    """Fetch recent Yahoo Finance headlines for a symbol (no API key)."""
    import urllib.parse
    import urllib.request
    from xml.etree import ElementTree as ET

    url = (
        "https://feeds.finance.yahoo.com/rss/2.0/headline?s="
        + urllib.parse.quote(symbol)
        + "&region=US&lang=en-US"
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        root = ET.fromstring(resp.read())
    titles = [item.findtext("title") or "" for item in root.iter("item")]
    return [t for t in titles if t][:limit]


@tool(
    "quote",
    description="Real point-in-time price/volume for a symbol (Yahoo, no key).",
    params=[{"name": "symbol", "type": "symbol", "required": True}],
    outputs=["price", "volume"],
)
def quote(symbol: str, ts: datetime | None = None, interval: str = "1d") -> dict[str, float]:
    """Price/volume as-of `ts` (the runner injects the tick timestamp). With no
    `ts` it returns the latest bar, so the live "Run now" path still works."""
    from .history import as_of

    px = as_of(symbol, ts, field="close", interval=interval)
    vol = as_of(symbol, ts, field="volume", interval=interval)
    return {"price": float(px) if px is not None else 0.0,
            "volume": float(vol) if vol is not None else 0.0}


@tool(
    "market_rel",
    description="Real market-relative signals (symbol vs ^GSPC) as-of a tick.",
    params=[{"name": "symbol", "type": "symbol", "required": True}],
    outputs=["vs_sp500_pct", "sector_volume"],
)
def market_rel(symbol: str, ts: datetime | None = None, interval: str = "1d") -> dict[str, float]:
    """The symbol's return minus the S&P 500's return over the last bar, as-of
    `ts`, plus the symbol's traded volume as a sector-volume proxy."""
    from .history import series_upto

    def _last_return(sym: str) -> float | None:
        bars = series_upto(sym, ts, interval=interval)
        if len(bars) < 2 or not bars[-2]["close"]:
            return None
        return (bars[-1]["close"] / bars[-2]["close"] - 1) * 100

    sym_ret = _last_return(symbol)
    spx_ret = _last_return("^GSPC")
    bars = series_upto(symbol, ts, interval=interval)
    vol = bars[-1]["volume"] if bars else 0.0
    rel = (sym_ret - spx_ret) if (sym_ret is not None and spx_ret is not None) else 0.0
    return {"vs_sp500_pct": round(rel, 4), "sector_volume": float(vol)}


@tool(
    "commodity_prices",
    description="Real gold/silver/bitcoin prices as-of a tick (Yahoo, no key).",
    params=[],
    outputs=["gold", "silver", "bitcoin"],
)
def commodity_prices(ts: datetime | None = None) -> dict[str, float]:
    """Gold (GC=F), silver (SI=F), bitcoin (BTC-USD) closes as-of `ts`. These
    are daily series regardless of the glyph interval."""
    from .history import as_of

    def _px(sym: str) -> float:
        v = as_of(sym, ts, field="close", interval="1d")
        return float(v) if v is not None else 0.0

    return {"gold": _px("GC=F"), "silver": _px("SI=F"), "bitcoin": _px("BTC-USD")}


@tool(
    "market_climate",
    description="Real volatility / rates / oil / dollar regime signals as-of a tick.",
    params=[],
    outputs=["vix", "yield_10y", "oil", "dollar"],
)
def market_climate(ts: datetime | None = None) -> dict[str, float]:
    """Macro climate as-of `ts`: ^VIX (fear), ^TNX (10y yield), CL=F (crude),
    DX-Y.NYB (dollar index). VIX is the honest point-in-time proxy for the
    market-fear signal that has no free historical headline feed."""
    from .history import as_of

    def _px(sym: str) -> float:
        v = as_of(sym, ts, field="close", interval="1d")
        return float(v) if v is not None else 0.0

    return {
        "vix": _px("^VIX"),
        "yield_10y": _px("^TNX"),
        "oil": _px("CL=F"),
        "dollar": _px("DX-Y.NYB"),
    }


def _auth_headers(cred: dict[str, str] | None) -> dict[str, str]:
    """Translate a decrypted credential into request headers."""
    if not cred:
        return {}
    kind = cred.get("kind")
    if kind == "bearer":
        return {"Authorization": f"Bearer {cred['token']}"}
    if kind == "header":
        return {cred["name"]: cred["value"]}
    if kind == "basic":
        import base64

        raw = f"{cred['username']}:{cred['password']}".encode()
        return {"Authorization": "Basic " + base64.b64encode(raw).decode()}
    return {}


@tool(
    "http_json",
    description="GET a JSON endpoint, optionally authenticated with a stored credential.",
    params=[{"name": "url", "type": "string", "required": True}],
    outputs=["(parsed JSON)"],
    cred_kind="bearer",
)
def http_json(url: str, cred: dict[str, str] | None = None) -> Any:
    """Fetch and parse a JSON endpoint. The runner injects `cred` when the step
    references a stored credential; the secret never reaches the browser."""
    import json
    import urllib.request

    headers = {"User-Agent": "stocks/1.0", "Accept": "application/json"}
    headers.update(_auth_headers(cred))
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
        return json.loads(resp.read())
