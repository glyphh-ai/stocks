"""Convert a step's mini-schema DSL into a JSON Schema for structured output.

A step declares its output shape compactly, e.g. {"score": "int[1..10]"}.
This expands to a strict JSON Schema object so Claude must return exactly
{"score": <int>} and nothing else.

The structured-output API only accepts the base JSON types (no minimum/maximum
keywords), so declared ranges like [1..10] are NOT sent to the API — they are
returned separately as `bounds` and enforced by clamping the parsed result.
The range still reaches the model via the step's prompt text.

Supported field types:
  int                -> integer
  int[lo..hi]        -> integer, clamped to [lo, hi]
  float / number     -> number
  float[lo..hi]      -> number, clamped to [lo, hi]
  str / string       -> string
  bool / boolean     -> boolean
"""

from __future__ import annotations

import re
from typing import Any

_RANGED = re.compile(r"^(int|float|number)\s*\[\s*(-?\d+(?:\.\d+)?)\s*\.\.\s*(-?\d+(?:\.\d+)?)\s*\]$")


def _field(spec: str) -> tuple[dict[str, Any], tuple[float, float] | None]:
    spec = spec.strip()
    m = _RANGED.match(spec)
    if m:
        kind, lo, hi = m.group(1), m.group(2), m.group(3)
        if kind == "int":
            return {"type": "integer"}, (int(lo), int(hi))
        return {"type": "number"}, (float(lo), float(hi))
    if spec == "int":
        return {"type": "integer"}, None
    if spec in ("float", "number"):
        return {"type": "number"}, None
    if spec in ("str", "string"):
        return {"type": "string"}, None
    if spec in ("bool", "boolean"):
        return {"type": "boolean"}, None
    raise ValueError(f"unsupported schema field spec: {spec!r}")


def to_json_schema(schema: dict[str, str]) -> dict[str, Any]:
    """Expand {key: spec} into a strict, API-safe JSON Schema object (types only)."""
    props = {key: _field(spec)[0] for key, spec in schema.items()}
    return {
        "type": "object",
        "properties": props,
        "required": list(schema.keys()),
        "additionalProperties": False,
    }


def bounds(schema: dict[str, str]) -> dict[str, tuple[float, float]]:
    """Return {key: (lo, hi)} for fields that declared a numeric range."""
    out: dict[str, tuple[float, float]] = {}
    for key, spec in schema.items():
        b = _field(spec)[1]
        if b is not None:
            out[key] = b
    return out


def clamp(values: dict[str, Any], schema: dict[str, str]) -> dict[str, Any]:
    """Clamp numeric fields to their declared ranges (defensive at the LLM edge)."""
    limits = bounds(schema)
    out = dict(values)
    for key, (lo, hi) in limits.items():
        if key in out and isinstance(out[key], (int, float)) and not isinstance(out[key], bool):
            out[key] = min(max(out[key], lo), hi)
    return out
