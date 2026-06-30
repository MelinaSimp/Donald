"""LLM streaming wrapper.

Exposes ``stream_text(messages)`` returning an async iterator of text deltas.
Two implementations:

  * ``anthropic_stream_text`` — the real one, using the official Anthropic SDK
    with streaming. Thinking is left off (the default on Opus 4.8): for a voice
    agent we want the first token out the door as fast as possible, and a
    thinking pass would add a silent delay before any audible word.

  * ``mock_stream_text`` — deterministic, dependency-free, token-by-token. Lets
    the whole app run and the tests pass with no API key.
"""

from __future__ import annotations

import asyncio
from typing import AsyncIterator

from . import config


async def mock_stream_text(messages: list[dict]) -> AsyncIterator[str]:
    """Yield a canned multi-sentence reply, one word-ish chunk at a time."""
    user = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user = m.get("content", "")
            break

    reply = (
        f"Sure, I can help with that. You said: {user.strip() or 'nothing yet'}. "
        "Here is the first thing to know. And here is a second, longer thought "
        "that takes a moment to say. That's everything for now."
    )
    # Emit in small chunks to exercise the sentence splitter the way a real
    # token stream would.
    for token in reply.split(" "):
        yield token + " "
        await asyncio.sleep(0.01)


async def anthropic_stream_text(messages: list[dict]) -> AsyncIterator[str]:
    """Stream text deltas from Claude via the official SDK."""
    import anthropic  # imported lazily so the mock path needs no dependency

    client = anthropic.AsyncAnthropic()
    async with client.messages.stream(
        model=config.LLM_MODEL,
        max_tokens=config.LLM_MAX_TOKENS,
        system=config.LLM_SYSTEM,
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text


def stream_text(messages: list[dict]) -> AsyncIterator[str]:
    """Pick the real or mock streamer based on config."""
    if config.USE_MOCK_LLM:
        return mock_stream_text(messages)
    return anthropic_stream_text(messages)
