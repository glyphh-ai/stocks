"""Placeholder resolution for job steps.

A bare "{verdict.score}" resolves to the raw value; placeholders embedded in
text ("Headlines: {news}") interpolate as strings.
"""

from __future__ import annotations

import re
from typing import Any

_PLACEHOLDER = re.compile(r"\{([^{}]+)\}")


def _lookup(ctx: dict[str, Any], path: str) -> Any:
    cur: Any = ctx
    for part in path.split("."):
        cur = cur[part] if isinstance(cur, dict) else getattr(cur, part)
    return cur


def resolve(value: Any, ctx: dict[str, Any]) -> Any:
    if isinstance(value, str):
        whole = _PLACEHOLDER.fullmatch(value.strip())
        if whole:
            return _lookup(ctx, whole.group(1).strip())
        return _PLACEHOLDER.sub(lambda m: str(_lookup(ctx, m.group(1).strip())), value)
    if isinstance(value, dict):
        return {k: resolve(v, ctx) for k, v in value.items()}
    if isinstance(value, list):
        return [resolve(v, ctx) for v in value]
    return value
