"""Stored credentials for tool steps.

GET    /credentials        -> list saved credentials (name + kind only)
POST   /credentials        -> create/replace a credential (secrets encrypted)
DELETE /credentials/{name}  -> remove a credential

Secret values are write-only: they are encrypted on the way in and never
returned. The job runner decrypts them server-side when a tool step runs.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..store_credentials import (
    delete_credential,
    list_credentials,
    set_credential,
)

router = APIRouter(prefix="/credentials", tags=["credentials"])


class CredentialMeta(BaseModel):
    name: str
    kind: str
    updated_at: datetime | None = None


class CredentialUpsert(BaseModel):
    name: str
    kind: str
    fields: dict[str, str] = Field(default_factory=dict)


@router.get("", response_model=list[CredentialMeta])
def get_credentials() -> list[CredentialMeta]:
    return [CredentialMeta(**c) for c in list_credentials()]


@router.post("", response_model=CredentialMeta)
def upsert_credential(payload: CredentialUpsert) -> CredentialMeta:
    if not payload.name.strip():
        raise HTTPException(400, "credential name is required")
    try:
        meta = set_credential(payload.name.strip(), payload.kind, payload.fields)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return CredentialMeta(**meta)


@router.delete("/{name}")
def remove_credential(name: str) -> dict[str, str]:
    if not delete_credential(name):
        raise HTTPException(404, f"credential not found: {name}")
    return {"deleted": name}
