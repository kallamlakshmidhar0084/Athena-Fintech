"""Async LLM client for Athena.

A single class with three methods:

- ``complete``   — text response
- ``stream``     — async iterator of text chunks
- ``structured`` — Pydantic-validated typed response (via ``instructor``)

Tracing happens automatically through ``langsmith.wrappers.wrap_anthropic``.
When called from inside a LangGraph node, pass the node's ``config`` so the
LLM span nests under the node's run instead of starting a new root.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, TypeVar

import instructor
from anthropic import AsyncAnthropic
from langsmith.run_helpers import tracing_context
from langsmith.run_trees import RunTree
from langsmith.wrappers import wrap_anthropic
from pydantic import BaseModel

from athena.config import settings

T = TypeVar("T", bound=BaseModel)


def _split_system(messages: list[dict]) -> tuple[str | None, list[dict]]:
    """Anthropic takes ``system`` as a separate parameter, not a message role."""
    if messages and messages[0].get("role") == "system":
        return messages[0]["content"], messages[1:]
    return None, messages


def _parent_run(config: dict | None) -> RunTree | None:
    """Build a LangSmith parent run from a LangGraph ``RunnableConfig``.

    Without this, LLM spans appear as top-level traces instead of nested
    under the node that issued the call.
    """
    if not config:
        return None
    try:
        return RunTree.from_runnable_config(config)
    except Exception:
        return None


class AsyncLLMClient:
    """Single async client. Imported as ``from athena.llm import llm``.

    Temperature defaults are deliberate:
    - complete / structured → 0.2 (analytical work, deterministic citations)
    - stream                → 0.4 (user-facing prose, slight warmth)
    """

    def __init__(self, model: str | None = None) -> None:
        self._model = model or settings.default_model
        self._max_tokens = settings.default_max_tokens
        anthropic = AsyncAnthropic(
            api_key=settings.anthropic_api_key.get_secret_value()
        )
        # Direct calls (complete/stream) go through the LangSmith-wrapped client
        # so they're auto-traced once LANGSMITH_TRACING is enabled.
        self._raw = wrap_anthropic(anthropic)
        # Instructor uses Anthropic's streaming API under the hood for structured
        # outputs. langsmith's wrap_anthropic._text_stream crashes when tracing
        # is disabled (it writes to a None run_tree). Hand instructor the
        # unwrapped client to avoid the bug; structured-call tracing will be
        # added back via @traceable in Phase 3 when we wire LangSmith fully.
        self._typed = instructor.from_anthropic(anthropic)

    @property
    def model(self) -> str:
        return self._model

    def _build_kwargs(
        self,
        messages: list[dict],
        temperature: float,
        max_tokens: int | None,
    ) -> dict[str, Any]:
        system, msgs = _split_system(messages)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "messages": msgs,
            "temperature": temperature,
            "max_tokens": max_tokens or self._max_tokens,
        }
        if system:
            kwargs["system"] = system
        return kwargs

    async def complete(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        tags: list[str] | None = None,
        config: dict | None = None,
    ) -> str:
        """Free-form text completion."""
        kwargs = self._build_kwargs(messages, temperature, max_tokens)
        with tracing_context(parent=_parent_run(config), tags=tags):
            response = await self._raw.messages.create(**kwargs)
        return response.content[0].text

    async def stream(
        self,
        messages: list[dict],
        *,
        temperature: float = 0.4,
        max_tokens: int | None = None,
        tags: list[str] | None = None,
        config: dict | None = None,
    ) -> AsyncIterator[str]:
        """Yield text chunks as they arrive."""
        kwargs = self._build_kwargs(messages, temperature, max_tokens)
        with tracing_context(parent=_parent_run(config), tags=tags):
            async with self._raw.messages.stream(**kwargs) as stream:
                async for chunk in stream.text_stream:
                    yield chunk

    async def structured(
        self,
        messages: list[dict],
        *,
        response_model: type[T],
        temperature: float = 0.2,
        max_tokens: int | None = None,
        max_retries: int = 2,
        tags: list[str] | None = None,
        config: dict | None = None,
    ) -> T:
        """Typed structured output. Validation + retries handled by ``instructor``."""
        kwargs = self._build_kwargs(messages, temperature, max_tokens)
        kwargs["response_model"] = response_model
        kwargs["max_retries"] = max_retries
        with tracing_context(parent=_parent_run(config), tags=tags):
            return await self._typed.messages.create(**kwargs)


llm = AsyncLLMClient()


# ---------------------------------------------------------------------------
# Smoke test — run as `uv run python -m athena.llm.client`
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio
    from typing import Literal

    class _SmokeVerdict(BaseModel):
        verdict: Literal["bullish", "bearish", "neutral"]
        reasoning: str

    async def _smoke() -> None:
        print(f"model: {llm.model}\n")

        print("[complete]")
        text = await llm.complete(
            [{"role": "user", "content": "Reply with the single word: ready"}]
        )
        print(f"  {text.strip()!r}\n")

        print("[stream]")
        print("  ", end="")
        async for chunk in llm.stream(
            [{"role": "user", "content": "Count from 1 to 5, one number per line."}]
        ):
            print(chunk, end="", flush=True)
        print("\n")

        print("[structured]")
        result = await llm.structured(
            [
                {
                    "role": "user",
                    "content": (
                        "Hypothetically, given strong AI demand and recent "
                        "earnings beats, classify NVIDIA's near-term outlook."
                    ),
                }
            ],
            response_model=_SmokeVerdict,
        )
        print(f"  {result.model_dump_json(indent=2)}\n")

        print("OK — all three methods work")

    asyncio.run(_smoke())
