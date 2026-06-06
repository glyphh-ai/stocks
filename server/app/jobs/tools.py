"""Registry of deterministic tool functions that job steps can call by name.

These are the ".py wrappers": pure-ish, no LLM. Register with @tool("name", ...)
and declare metadata (params, outputs, credential kind) so the config UI can
offer the tool in a dropdown and render the right inputs. Adding a new data
source = adding one @tool here; the builder needs no changes beyond the creds.
"""

from __future__ import annotations

import hashlib
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
    description="Stub price/volume for a symbol (deterministic).",
    params=[{"name": "symbol", "type": "symbol", "required": True}],
    outputs=["price", "volume"],
)
def quote(symbol: str) -> dict[str, float]:
    """Deterministic stub price/volume, seeded by symbol. Swap for a real feed later."""
    return {
        "price": round(50 + _unit(symbol, "price") * 350, 2),
        "volume": round(1_000_000 + _unit(symbol, "volume") * 49_000_000),
    }


@tool(
    "market_rel",
    description="Stub market-relative signals for a symbol (deterministic).",
    params=[{"name": "symbol", "type": "symbol", "required": True}],
    outputs=["vs_sp500_pct", "sector_volume"],
)
def market_rel(symbol: str) -> dict[str, float]:
    """Deterministic stub market-relative signals, seeded by symbol."""
    return {
        "vs_sp500_pct": round(-3 + _unit(symbol, "sp500") * 6, 2),
        "sector_volume": round(_unit(symbol, "sector") * 100_000_000),
    }


@tool(
    "commodity_prices",
    description="Stub gold/silver/bitcoin prices (deterministic).",
    params=[],
    outputs=["gold", "silver", "bitcoin"],
)
def commodity_prices() -> dict[str, float]:
    """Deterministic stub commodity prices (symbol-independent)."""
    return {"gold": 2300.0, "silver": 29.0, "bitcoin": 68000.0}


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
