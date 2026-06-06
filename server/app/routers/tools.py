"""Tool palette for the config UI.

GET /tools -> every registered job tool with its metadata (params it takes,
outputs it returns, and which credential kind it accepts), so the segment
editor can offer tools in a dropdown and render the right inputs.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from ..jobs import list_tool_specs

router = APIRouter(prefix="/tools", tags=["tools"])


class ToolParam(BaseModel):
    name: str
    type: str = "string"
    required: bool = True


class ToolSpec(BaseModel):
    name: str
    description: str
    params: list[ToolParam]
    outputs: list[str]
    cred_kind: str
    config: list[ToolParam]


@router.get("", response_model=list[ToolSpec])
def list_tools() -> list[dict[str, Any]]:
    return list_tool_specs()
