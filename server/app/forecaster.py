"""LLM forecaster: a persistent, tool-using Claude dialogue per symbol.

The ensemble predictor blends several mechanical sources (autoregressive, beam,
trades). This module is the LLM voice — and it is deliberately heavier than a
one-shot prompt:

  - **Tools.** Claude is given a `get_glyph_history` tool that returns the full
    structured glyph history (every recorded interval's scalar signal values,
    their ranges, and the beam's projection for the next step). It pulls as much
    of that history into context as it wants before committing to a view. It
    answers via a `submit_forecast` tool whose schema *is* the structured output
    (per-signal directional bias + confidence).

  - **Persistent conversation.** The message array is stored per (symbol,
    interval) and carried from one prediction to the next, so the model's
    running reasoning about regime and how its prior calls fared accumulates
    rather than resetting each interval.

  - **Compaction.** Server-side compaction (with a custom instruction prompt
    tuned for this forecasting loop) keeps the growing dialogue bounded while
    preserving the forecasting narrative.

The returned per-signal biases feed `predictor._predict_signals`, where the
LLM nudge is scaled into the blended next value.
"""

from __future__ import annotations

import json
from typing import Any

import numpy as np
from sqlalchemy.orm import Session

from .config import settings
from .models import PredictionConversation
from .predict import _role_value, _scalar_roles

# Beta for server-side compaction of the running conversation.
_COMPACT_BETA = "compact-2026-01-12"
# Compact once the dialogue's input grows past this; raw glyph-history tool
# dumps are re-fetchable, so we can summarize them away aggressively.
_COMPACT_TRIGGER = 120_000

_MAX_TURNS = 6  # tool round-trips before we give up waiting for a forecast

_SYSTEM = (
    "You are a quantitative signal forecaster maintaining one continuous "
    "forecasting dialogue for a single market symbol. Each interval you are "
    "asked to project the next-interval direction of normalized market signals "
    "(scalar roles of a hyperdimensional 'glyph'). You have a get_glyph_history "
    "tool that returns the full structured history of every signal plus the "
    "beam-search projection for the next interval — call it to inspect as much "
    "history as you need before forming a view, and re-call it later when you "
    "want fresh numbers. When you are ready, call submit_forecast exactly once "
    "with, for each signal you have a view on, a directional bias in [-1, 1] "
    "(negative = expect it to fall, positive = rise, 0 = no view) and a "
    "confidence in [0, 1]. Be conservative: only nudge signals the history or "
    "trade record genuinely supports. Because this dialogue persists across "
    "intervals, carry forward what you learned — note regimes, couplings, and "
    "whether your last calls were borne out. Do not give financial advice."
)

# Custom summarization prompt for the compaction edit: keep the forecasting
# narrative, drop the bulky tool dumps.
_COMPACT_INSTRUCTIONS = (
    "This is a long-running market-forecasting dialogue for one symbol. When "
    "you compact it, preserve: the symbol and interval; the most recent "
    "per-signal directional biases issued and their confidence; any durable "
    "observations about regime, trend, volatility shifts, and couplings between "
    "signals built up across intervals; and any notes on how earlier forecasts "
    "fared against what printed. Discard the verbose raw glyph-history tool "
    "results — they can be re-fetched at any time with get_glyph_history. Keep "
    "the running forecasting narrative compact but continuous so the next "
    "interval's forecast builds on the reasoning so far."
)

_GLYPH_HISTORY_TOOL: dict[str, Any] = {
    "name": "get_glyph_history",
    "description": (
        "Return the full structured glyph history for this symbol: for every "
        "recorded interval, the value of each scalar signal, plus each signal's "
        "[low, high] range and the beam-search projection for the next "
        "interval. Use it to inspect the trajectory before forecasting."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "last_n": {
                "type": "integer",
                "description": (
                    "Only return the most recent N intervals. Omit for the "
                    "entire history."
                ),
            },
            "signals": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Only return these signal paths. Omit for all signals."
                ),
            },
        },
        "additionalProperties": False,
    },
}

_SUBMIT_FORECAST_TOOL: dict[str, Any] = {
    "name": "submit_forecast",
    "description": (
        "Submit your final per-signal directional forecast for the next "
        "interval. Call this exactly once when you are done inspecting history."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "signals": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "bias": {"type": "number"},
                        "confidence": {"type": "number"},
                    },
                    "required": ["path", "bias", "confidence"],
                    "additionalProperties": False,
                },
            },
            "rationale": {"type": "string"},
            "overall_confidence": {"type": "number"},
        },
        "required": ["signals", "rationale", "overall_confidence"],
        "additionalProperties": False,
    },
}


def _structured_history(
    history: list[dict],
    roles: list[tuple[str, tuple[float, float]]],
    beam_vals: dict[str, float],
    *,
    last_n: int | None = None,
    only: set[str] | None = None,
) -> dict[str, Any]:
    """Build the get_glyph_history payload: per-interval signal values."""
    sel = [(p, rng) for p, rng in roles if only is None or p in only]
    rows = history[-last_n:] if last_n else history
    intervals = [
        {
            "ts": str(h["ts"]),
            "signals": {
                p: (round(v, 6) if (v := _role_value(h["glyph"], p)) is not None else None)
                for p, _ in sel
            },
        }
        for h in rows
    ]
    return {
        "symbol": history[-1]["glyph"].get("symbol"),
        "n_intervals": len(intervals),
        "ranges": {p: [lo, hi] for p, (lo, hi) in sel},
        "beam_projection": {
            p: round(beam_vals[p], 6) for p, _ in sel if p in beam_vals
        },
        "intervals": intervals,
    }


def _load_messages(session: Session, symbol: str, interval: str) -> list[dict]:
    row = (
        session.query(PredictionConversation)
        .filter(
            PredictionConversation.symbol == symbol,
            PredictionConversation.interval == interval,
        )
        .first()
    )
    return list(row.messages) if row and row.messages else []


def _save_messages(
    session: Session, symbol: str, interval: str, messages: list[dict]
) -> None:
    row = (
        session.query(PredictionConversation)
        .filter(
            PredictionConversation.symbol == symbol,
            PredictionConversation.interval == interval,
        )
        .first()
    )
    if row is None:
        session.add(
            PredictionConversation(
                symbol=symbol, interval=interval, messages=messages
            )
        )
    else:
        row.messages = messages
    session.commit()


async def llm_forecast(
    session: Session,
    symbol: str,
    interval: str,
    history: list[dict],
    beam_vals: dict[str, float],
    trade_bias: dict[str, float],
) -> tuple[dict[str, float], float | None, dict[str, Any] | None]:
    """Run the persistent tool-using forecast. No key -> empty (skipped).

    Returns (per-signal bias, overall confidence, the raw submitted forecast).
    """
    if not settings.anthropic_api_key:
        return {}, None, None

    roles = _scalar_roles(history[-1]["glyph"])
    valid = {p for p, _ in roles}

    messages = _load_messages(session, symbol, interval)
    target_ts = str(history[-1]["ts"])
    messages.append(
        {
            "role": "user",
            "content": (
                "Forecast the next interval after "
                f"{target_ts} (symbol {symbol}, {interval}).\n"
                "Beam projection for next interval: "
                + json.dumps({p: round(v, 4) for p, v in beam_vals.items()})
                + "\nTrade-derived directional bias: "
                + json.dumps({p: round(v, 4) for p, v in trade_bias.items()})
                + "\nInspect the structured history with get_glyph_history as "
                "needed, then call submit_forecast once."
            ),
        }
    )

    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    forecast: dict[str, Any] | None = None

    for _ in range(_MAX_TURNS):
        resp = await client.beta.messages.create(
            model=settings.anthropic_model,
            max_tokens=2000,
            thinking={"type": "disabled"},
            system=[{"type": "text", "text": _SYSTEM}],
            tools=[_GLYPH_HISTORY_TOOL, _SUBMIT_FORECAST_TOOL],
            messages=messages,
            context_management={
                "edits": [
                    {
                        "type": "compact_20260112",
                        "instructions": _COMPACT_INSTRUCTIONS,
                        "trigger": {"type": "input_tokens", "value": _COMPACT_TRIGGER},
                    }
                ]
            },
            betas=[_COMPACT_BETA],
        )

        # Persist every content block (incl. any compaction block) so the
        # dialogue stays valid and continuous on the next interval.
        assistant_content = [
            b.model_dump(mode="json", exclude_none=True) for b in resp.content
        ]
        messages.append({"role": "assistant", "content": assistant_content})

        if resp.stop_reason != "tool_use":
            break

        tool_results: list[dict] = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            if block.name == "get_glyph_history":
                args = block.input or {}
                only = (
                    {s for s in args.get("signals", []) if s in valid}
                    if args.get("signals")
                    else None
                )
                payload = _structured_history(
                    history,
                    roles,
                    beam_vals,
                    last_n=args.get("last_n"),
                    only=only,
                )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": json.dumps(payload, default=str),
                    }
                )
            elif block.name == "submit_forecast":
                forecast = dict(block.input or {})
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": "Forecast recorded.",
                    }
                )

        # Answer every tool_use so the stored conversation never ends on an
        # unresolved call (the next interval would 400 otherwise).
        if tool_results:
            messages.append({"role": "user", "content": tool_results})
        if forecast is not None:
            break

    _save_messages(session, symbol, interval, messages)

    if forecast is None:
        return {}, None, None

    bias = {
        s["path"]: float(np.clip(s["bias"], -1.0, 1.0))
        for s in forecast.get("signals", [])
        if s.get("path") in valid
    }
    overall = forecast.get("overall_confidence")
    return bias, (float(overall) if overall is not None else None), forecast


def reset_conversation(session: Session, symbol: str, interval: str) -> None:
    """Drop the stored dialogue (e.g. when the symbol's history is cleared)."""
    session.query(PredictionConversation).filter(
        PredictionConversation.symbol == symbol,
        PredictionConversation.interval == interval,
    ).delete(synchronize_session=False)
    session.commit()
