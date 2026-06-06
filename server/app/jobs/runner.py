"""Deterministic glyph job orchestrator.

run_glyph runs each layer's segment jobs (sequential or parallel per the
layer's `execution` setting), fills role values into a copy of the template,
then encodes + persists a new temporal glyph version. Weights already declared
on roles/segments/layers apply at encode time — jobs only fill values.
"""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from ..storage import write_glyph
from ..store_credentials import get_credential_secret
from .context import resolve
from .executor import LLMExecutor
from .tools import get_tool


async def _call_tool(
    name: str, args: dict[str, Any], cred: dict[str, str] | None = None
) -> Any:
    fn = get_tool(name)
    if cred is not None:
        args = {**args, "cred": cred}
    if asyncio.iscoroutinefunction(fn):
        return await fn(**args)
    return await asyncio.to_thread(fn, **args)


async def run_segment(
    segment: dict, base_ctx: dict[str, Any], executor: LLMExecutor
) -> dict[str, Any]:
    """Execute a segment's steps in order; return {role_key: value}."""
    ctx = dict(base_ctx)
    role_values: dict[str, Any] = {}
    for step in segment.get("job", []):
        kind = step["kind"]
        if kind == "tool":
            cred = None
            cred_name = step.get("credential")
            if cred_name:
                cred = get_credential_secret(cred_name)
                if cred is None:
                    raise KeyError(f"no credential stored as {cred_name!r}")
            ctx[step["out"]] = await _call_tool(
                step["name"], resolve(step.get("args", {}), ctx), cred
            )
        elif kind == "llm":
            ctx[step["out"]] = await executor.run(
                system=resolve(step.get("system", ""), ctx),
                prompt=resolve(step.get("prompt", ""), ctx),
                schema=step.get("schema", {}),
                step_name=step.get("out", segment["key"]),
            )
        elif kind == "set_role":
            role_values[step["role"]] = resolve(step["value"], ctx)
        else:
            raise ValueError(f"unknown step kind: {kind!r}")
    return role_values


async def run_layer(
    layer: dict, base_ctx: dict[str, Any], executor: LLMExecutor
) -> dict[str, dict[str, Any]]:
    segments = layer.get("segments", [])
    if layer.get("execution") == "parallel":
        results = await asyncio.gather(
            *(run_segment(s, base_ctx, executor) for s in segments)
        )
    else:
        results = [await run_segment(s, base_ctx, executor) for s in segments]
    return {s["key"]: r for s, r in zip(segments, results)}


async def run_glyph(
    template: dict,
    symbol: str,
    interval: str,
    ts: datetime,
    executor: LLMExecutor,
    session: Session,
) -> tuple[int, dict]:
    """Run all jobs, fill the template, persist a new version. Layers run in order."""
    base_ctx = {"symbol": symbol, "interval": interval}
    filled = copy.deepcopy(template)
    filled["interval"] = interval

    for layer in filled.get("layers", []):
        seg_results = await run_layer(layer, base_ctx, executor)
        for seg in layer.get("segments", []):
            values = seg_results.get(seg["key"], {})
            for role in seg.get("roles", []):
                if role["key"] in values:
                    role["value"] = values[role["key"]]

    version_id = write_glyph(session, symbol, interval, ts, filled)
    return version_id, filled
