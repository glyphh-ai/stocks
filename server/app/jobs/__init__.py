from .executor import AnthropicLLMExecutor, LLMExecutor, StubLLMExecutor
from .runner import run_glyph, run_layer, run_segment
from .tools import get_tool, list_tool_specs, register, tool


def default_executor() -> LLMExecutor:
    """Real Claude when an API key is configured, else a stub that refuses.

    The stub has no canned outputs, so an `llm` step will raise unless a key is
    present — failing loud rather than silently fabricating scores.
    """
    from ..config import settings

    if settings.anthropic_api_key:
        return AnthropicLLMExecutor(
            api_key=settings.anthropic_api_key, model=settings.anthropic_model
        )
    return StubLLMExecutor({})


__all__ = [
    "AnthropicLLMExecutor",
    "LLMExecutor",
    "StubLLMExecutor",
    "default_executor",
    "run_glyph",
    "run_layer",
    "run_segment",
    "get_tool",
    "list_tool_specs",
    "register",
    "tool",
]
