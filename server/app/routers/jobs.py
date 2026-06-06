"""Trigger a glyph job run: fetch via tools, judge via the LLM, persist a version.

POST /jobs/run runs every layer's segment jobs against `symbol`/`interval`, fills
the template, and writes a new temporal glyph. The executor is real Claude when
ANTHROPIC_API_KEY is set, otherwise a stub that refuses `llm` steps — so a run
with news_sentiment needs a key, but a tool-only template works offline.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..db import PgSession
from ..jobs import default_executor, run_glyph
from ..jobs.runner import run_segment

router = APIRouter(prefix="/jobs", tags=["jobs"])

_TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "hdc" / "examples"


class RunRequest(BaseModel):
    symbol: str
    interval: str = "1m"
    ts: datetime | None = None
    template: dict[str, Any] | None = None
    template_name: str = "equity.template.json"


class RunResponse(BaseModel):
    version_id: int
    symbol: str
    interval: str
    ts: datetime
    roles: dict[str, Any] = Field(default_factory=dict)


def _load_template(req: RunRequest) -> dict[str, Any]:
    if req.template is not None:
        return req.template
    path = _TEMPLATE_DIR / req.template_name
    if not path.is_file():
        raise HTTPException(404, f"template not found: {req.template_name}")
    return json.loads(path.read_text())


def _flatten_roles(filled: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for layer in filled.get("layers", []):
        for seg in layer.get("segments", []):
            for role in seg.get("roles", []):
                if "value" in role:
                    out[f"{layer['key']}/{seg['key']}/{role['key']}"] = role["value"]
    return out


class TestSegmentRequest(BaseModel):
    symbol: str = "TEST"
    interval: str = "1m"
    segment: dict[str, Any]


class TestSegmentResponse(BaseModel):
    roles: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


@router.post("/test-segment", response_model=TestSegmentResponse)
async def test_segment(req: TestSegmentRequest) -> TestSegmentResponse:
    """Run a single segment's job in isolation and return the role values it sets.

    Drives the config UI's test panel — no glyph is persisted. Uses the real
    Claude executor when a key is set, else the stub (which refuses llm steps).
    """
    base_ctx = {"symbol": req.symbol, "interval": req.interval}
    try:
        roles = await run_segment(req.segment, base_ctx, default_executor())
        return TestSegmentResponse(roles=roles)
    except Exception as exc:  # noqa: BLE001 - surface the failure to the UI
        return TestSegmentResponse(error=f"{type(exc).__name__}: {exc}")


@router.post("/run", response_model=RunResponse)
async def run(req: RunRequest) -> RunResponse:
    template = _load_template(req)
    ts = req.ts or datetime.now(timezone.utc)
    executor = default_executor()

    session = PgSession()
    try:
        version_id, filled = await run_glyph(
            template, req.symbol, req.interval, ts, executor, session
        )
    finally:
        session.close()

    return RunResponse(
        version_id=version_id,
        symbol=req.symbol,
        interval=req.interval,
        ts=ts,
        roles=_flatten_roles(filled),
    )
