"""LLM executors: one interface, a deterministic stub and the real Claude one.

An `llm` step calls executor.run(...) with its own system prompt and an output
schema, and gets back a structured dict. The orchestrator owns the flow; the
executor only judges.
"""

from __future__ import annotations

import json
from typing import Any, Protocol, runtime_checkable

from .schema import clamp, to_json_schema


@runtime_checkable
class LLMExecutor(Protocol):
    async def run(
        self, *, system: str, prompt: str, schema: dict[str, str], step_name: str
    ) -> dict[str, Any]: ...


class StubLLMExecutor:
    """Returns canned outputs keyed by step name. Deterministic, for tests."""

    def __init__(self, canned: dict[str, dict[str, Any]]):
        self._canned = canned

    async def run(
        self, *, system: str, prompt: str, schema: dict[str, str], step_name: str
    ) -> dict[str, Any]:
        if step_name not in self._canned:
            raise KeyError(f"StubLLMExecutor has no canned output for {step_name!r}")
        return self._canned[step_name]


class AnthropicLLMExecutor:
    """Judges each `llm` step with a real Claude call returning structured JSON.

    The step's mini-schema (e.g. {"score": "int[1..10]"}) is expanded to a JSON
    Schema and enforced via output_config, so the reply is exactly that object.
    The system prompt is cached — it's stable across the many per-minute runs.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-opus-4-7",
        max_tokens: int = 1024,
    ):
        from anthropic import AsyncAnthropic

        self._client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    async def run(
        self, *, system: str, prompt: str, schema: dict[str, str], step_name: str
    ) -> dict[str, Any]:
        json_schema = to_json_schema(schema)
        resp = await self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            thinking={"type": "disabled"},
            system=[
                {
                    "type": "text",
                    "text": system,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": json_schema,
                }
            },
        )
        text = "".join(b.text for b in resp.content if b.type == "text")
        return clamp(json.loads(text), schema)
