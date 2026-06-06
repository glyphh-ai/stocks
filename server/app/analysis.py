"""Analyze the glyph conditions around a trade.

gather_conditions() pulls the role values at the trade's entry and exit
versions plus the per-layer drift between them — i.e. which parts of the HDC
snapshot moved over the life of the trade. analyze_trade() hands those
conditions to Claude for a narrative read on what affected the outcome; with no
API key it returns the raw conditions and a deterministic summary instead.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from .config import settings
from .models import GlyphVersion, Trade
from .storage import drift_between

_SYSTEM = (
    "You are a trading analyst. You are given the encoded market conditions "
    "(role values from a hyperdimensional 'glyph') at the entry and exit of a "
    "single trade, plus how much each layer of the glyph drifted over the "
    "trade. Explain which conditions most plausibly affected the trade's "
    "outcome. Be concrete and cite specific roles and drift values. Do not "
    "give financial advice."
)

_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_factors": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "factor": {"type": "string"},
                    "observation": {"type": "string"},
                    "influence": {
                        "type": "string",
                        "enum": ["supportive", "adverse", "neutral"],
                    },
                },
                "required": ["factor", "observation", "influence"],
                "additionalProperties": False,
            },
        },
        "outlook": {"type": "string"},
    },
    "required": ["summary", "key_factors", "outlook"],
    "additionalProperties": False,
}


def _roles(glyph: dict | None) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not glyph:
        return out
    for layer in glyph.get("layers", []):
        for seg in layer.get("segments", []):
            for role in seg.get("roles", []):
                if "value" in role:
                    out[f"{layer['key']}/{seg['key']}/{role['key']}"] = role["value"]
    return out


def _layer_keys(glyph: dict | None) -> list[str]:
    return [l["key"] for l in (glyph or {}).get("layers", [])]


def gather_conditions(session: Session, trade: Trade) -> dict[str, Any]:
    """Role values at entry/exit, their numeric deltas, and per-layer drift."""
    entry_v = (
        session.get(GlyphVersion, trade.entry_version_id)
        if trade.entry_version_id
        else None
    )
    exit_v = (
        session.get(GlyphVersion, trade.exit_version_id)
        if trade.exit_version_id
        else None
    )
    entry_roles = _roles(entry_v.glyph if entry_v else None)
    exit_roles = _roles(exit_v.glyph if exit_v else None)

    deltas: dict[str, float] = {}
    if exit_roles:
        for path, ev in entry_roles.items():
            xv = exit_roles.get(path)
            if isinstance(ev, (int, float)) and isinstance(xv, (int, float)):
                deltas[path] = round(float(xv) - float(ev), 4)

    drift: dict[str, float] = {}
    if entry_v and exit_v and entry_v.id != exit_v.id:
        paths = ["cortex"] + [f"layer:{k}" for k in _layer_keys(entry_v.glyph)]
        for p in paths:
            try:
                drift[p] = round(drift_between(session, entry_v.id, exit_v.id, p), 4)
            except Exception:  # noqa: BLE001 - missing node path, skip it
                continue

    return {
        "trade": {
            "symbol": trade.symbol,
            "side": trade.side,
            "status": trade.status,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "volume": trade.volume,
            "pnl": trade.pnl,
            "entry_ts": trade.entry_ts.isoformat() if trade.entry_ts else None,
            "exit_ts": trade.exit_ts.isoformat() if trade.exit_ts else None,
        },
        "entry_roles": entry_roles,
        "exit_roles": exit_roles or None,
        "role_deltas": deltas or None,
        "layer_drift": drift or None,
    }


def _deterministic_summary(c: dict[str, Any]) -> str:
    t = c["trade"]
    parts = [f"{t['side']} {t['symbol']}"]
    if t["pnl"] is not None:
        parts.append(f"realized P&L {t['pnl']:+.2f}")
    if c.get("layer_drift"):
        top = sorted(
            c["layer_drift"].items(), key=lambda kv: kv[1], reverse=True
        )[:2]
        moved = ", ".join(f"{k} drifted {v:.3f}" for k, v in top)
        parts.append(f"largest condition shift: {moved}")
    return "; ".join(parts) + "."


async def analyze_trade(session: Session, trade: Trade) -> dict[str, Any]:
    """Conditions plus an LLM read of them (or a deterministic summary, no key)."""
    conditions = gather_conditions(session, trade)

    if not settings.anthropic_api_key:
        return {
            "conditions": conditions,
            "llm_available": False,
            "analysis": {
                "summary": _deterministic_summary(conditions),
                "key_factors": [],
                "outlook": "Set ANTHROPIC_API_KEY for a full LLM analysis.",
            },
        }

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    resp = await client.messages.create(
        model=settings.anthropic_model,
        max_tokens=1500,
        thinking={"type": "disabled"},
        system=[{"type": "text", "text": _SYSTEM}],
        messages=[
            {
                "role": "user",
                "content": "Analyze this trade's conditions:\n"
                + json.dumps(conditions, default=str),
            }
        ],
        output_config={"format": {"type": "json_schema", "schema": _SCHEMA}},
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return {
        "conditions": conditions,
        "llm_available": True,
        "analysis": json.loads(text),
    }
