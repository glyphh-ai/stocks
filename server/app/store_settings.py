"""Application settings — currently the trade-fee model.

A single row (id=1) holds the fee config a brokerage would charge. Fees are
applied per leg (entry and exit) so a round-trip trade pays twice.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from .models import AppSettings


def get_settings(session: Session) -> AppSettings:
    """The settings row, created with defaults if it does not yet exist."""
    s = session.get(AppSettings, 1)
    if s is None:
        s = AppSettings(id=1, commission_per_trade=0.0, per_share=0.0, percent=0.0)
        session.add(s)
        session.commit()
        session.refresh(s)
    return s


def update_settings(
    session: Session,
    commission_per_trade: float,
    per_share: float,
    percent: float,
) -> AppSettings:
    s = get_settings(session)
    s.commission_per_trade = commission_per_trade
    s.per_share = per_share
    s.percent = percent
    session.commit()
    session.refresh(s)
    return s


def leg_fee(s: AppSettings, price: float, volume: float) -> float:
    """Cost of one leg: flat commission + per-share + percent of notional."""
    notional = abs(price) * abs(volume)
    fee = s.commission_per_trade + s.per_share * abs(volume) + (s.percent / 100.0) * notional
    return round(fee, 2)
