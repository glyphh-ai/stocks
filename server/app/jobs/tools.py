"""Registry of deterministic tool functions that job steps can call by name.

These are the ".py wrappers": pure-ish, no LLM. Register with @tool("name").
"""

from __future__ import annotations

from typing import Callable

_REGISTRY: dict[str, Callable] = {}


def tool(name: str) -> Callable[[Callable], Callable]:
    def deco(fn: Callable) -> Callable:
        _REGISTRY[name] = fn
        return fn

    return deco


def register(name: str, fn: Callable) -> None:
    """Imperative register/override (used by demos and tests)."""
    _REGISTRY[name] = fn


def get_tool(name: str) -> Callable:
    if name not in _REGISTRY:
        raise KeyError(f"no tool registered as {name!r}")
    return _REGISTRY[name]


@tool("yahoo_news")
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
