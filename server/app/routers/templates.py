"""Persisted glyph templates built in the config UI.

GET    /templates           -> list saved templates (metadata only)
GET    /templates/{name}     -> full template body
PUT    /templates/{name}     -> upsert a template
DELETE /templates/{name}     -> remove a template
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from ..db import PgSession
from ..models import GlyphTemplate

router = APIRouter(prefix="/templates", tags=["templates"])

_EXAMPLE = Path(__file__).resolve().parent.parent / "hdc" / "examples" / "equity.template.json"


class TemplateMeta(BaseModel):
    name: str
    symbol: str
    updated_at: datetime | None = None


class TemplateBody(BaseModel):
    name: str
    symbol: str = ""
    body: dict[str, Any]
    updated_at: datetime | None = None


class TemplateUpsert(BaseModel):
    symbol: str = ""
    body: dict[str, Any] = Field(default_factory=dict)


@router.get("", response_model=list[TemplateMeta])
def list_templates() -> list[TemplateMeta]:
    session = PgSession()
    try:
        rows = session.scalars(select(GlyphTemplate).order_by(GlyphTemplate.name)).all()
        return [
            TemplateMeta(name=t.name, symbol=t.symbol, updated_at=t.updated_at)
            for t in rows
        ]
    finally:
        session.close()


@router.get("/{name}", response_model=TemplateBody)
def get_template(name: str) -> TemplateBody:
    session = PgSession()
    try:
        t = session.scalar(select(GlyphTemplate).where(GlyphTemplate.name == name))
        if t is None:
            # Seed convenience: expose the bundled example without a save.
            if name == "equity" and _EXAMPLE.is_file():
                return TemplateBody(name="equity", symbol="AAPL", body=json.loads(_EXAMPLE.read_text()))
            raise HTTPException(404, f"template not found: {name}")
        return TemplateBody(name=t.name, symbol=t.symbol, body=t.body, updated_at=t.updated_at)
    finally:
        session.close()


@router.put("/{name}", response_model=TemplateBody)
def upsert_template(name: str, payload: TemplateUpsert) -> TemplateBody:
    session = PgSession()
    try:
        t = session.scalar(select(GlyphTemplate).where(GlyphTemplate.name == name))
        if t is None:
            t = GlyphTemplate(name=name, symbol=payload.symbol, body=payload.body)
            session.add(t)
        else:
            t.symbol = payload.symbol
            t.body = payload.body
        session.commit()
        session.refresh(t)
        return TemplateBody(name=t.name, symbol=t.symbol, body=t.body, updated_at=t.updated_at)
    finally:
        session.close()


@router.delete("/{name}")
def delete_template(name: str) -> dict[str, str]:
    session = PgSession()
    try:
        t = session.scalar(select(GlyphTemplate).where(GlyphTemplate.name == name))
        if t is None:
            raise HTTPException(404, f"template not found: {name}")
        session.delete(t)
        session.commit()
        return {"deleted": name}
    finally:
        session.close()
