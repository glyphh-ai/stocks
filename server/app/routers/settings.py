"""Application settings — the trade-fee model used to net trade P&L.

GET /settings -> current fee config
PUT /settings -> replace fee config
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..db import PgSession
from ..store_settings import get_settings, update_settings

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsOut(BaseModel):
    commission_per_trade: float
    per_share: float
    percent: float
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class SettingsIn(BaseModel):
    commission_per_trade: float = Field(0.0, ge=0)
    per_share: float = Field(0.0, ge=0)
    percent: float = Field(0.0, ge=0)


@router.get("", response_model=SettingsOut)
def read_settings() -> SettingsOut:
    session = PgSession()
    try:
        return SettingsOut.model_validate(get_settings(session))
    finally:
        session.close()


@router.put("", response_model=SettingsOut)
def write_settings(payload: SettingsIn) -> SettingsOut:
    session = PgSession()
    try:
        s = update_settings(
            session,
            commission_per_trade=payload.commission_per_trade,
            per_share=payload.per_share,
            percent=payload.percent,
        )
        return SettingsOut.model_validate(s)
    finally:
        session.close()
