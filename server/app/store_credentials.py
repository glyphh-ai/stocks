"""Encrypted credential CRUD, shared by the API router and the job runner.

Secret fields are encrypted with app.crypto before they touch the DB and are
only decrypted here, server-side. The HTTP layer surfaces names/kinds — never
the secret values. Each kind declares which fields it carries:

    bearer  -> {"token"}
    basic   -> {"username", "password"}
    header  -> {"name", "value"}
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from .crypto import decrypt, encrypt
from .db import PgSession
from .models import Credential

CRED_FIELDS: dict[str, list[str]] = {
    "bearer": ["token"],
    "basic": ["username", "password"],
    "header": ["name", "value"],
}


def list_credentials() -> list[dict[str, Any]]:
    """Non-secret metadata for every stored credential."""
    session = PgSession()
    try:
        rows = session.scalars(select(Credential).order_by(Credential.name)).all()
        return [
            {"name": c.name, "kind": c.kind, "updated_at": c.updated_at}
            for c in rows
        ]
    finally:
        session.close()


def set_credential(name: str, kind: str, fields: dict[str, str]) -> dict[str, Any]:
    """Create or replace a credential. Returns non-secret metadata only."""
    if kind not in CRED_FIELDS:
        raise ValueError(f"unknown credential kind: {kind!r}")
    missing = [f for f in CRED_FIELDS[kind] if not fields.get(f)]
    if missing:
        raise ValueError(f"missing fields for {kind}: {', '.join(missing)}")
    payload = {f: fields[f] for f in CRED_FIELDS[kind]}
    enc = encrypt(json.dumps(payload))

    session = PgSession()
    try:
        c = session.scalar(select(Credential).where(Credential.name == name))
        if c is None:
            c = Credential(name=name, kind=kind, enc=enc)
            session.add(c)
        else:
            c.kind = kind
            c.enc = enc
        session.commit()
        session.refresh(c)
        return {"name": c.name, "kind": c.kind, "updated_at": c.updated_at}
    finally:
        session.close()


def delete_credential(name: str) -> bool:
    session = PgSession()
    try:
        c = session.scalar(select(Credential).where(Credential.name == name))
        if c is None:
            return False
        session.delete(c)
        session.commit()
        return True
    finally:
        session.close()


def get_credential_secret(name: str) -> dict[str, str] | None:
    """Decrypt a credential for server-side use. Returns {"kind", **fields}."""
    session = PgSession()
    try:
        c = session.scalar(select(Credential).where(Credential.name == name))
        if c is None:
            return None
        fields = json.loads(decrypt(c.enc))
        return {"kind": c.kind, **fields}
    finally:
        session.close()
