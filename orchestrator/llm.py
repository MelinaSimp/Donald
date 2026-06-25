"""Thin wrapper over the Anthropic Messages API.

Keeps the SDK call shape in one place so the agent loop reads cleanly and the
model/effort defaults are easy to audit. Uses adaptive thinking (the model
decides when and how much to think) — the recommended mode for current models.
"""

from __future__ import annotations

from typing import Any

import anthropic

# Default to the most capable Opus-tier model. Individual agents override this
# in their manifest — cheaper models for cheap work (Tier 2: model per agent).
DEFAULT_MODEL = "claude-opus-4-8"


class LLM:
    """A single completion call. The agentic loop lives in agent.py."""

    def __init__(self, client: anthropic.Anthropic | None = None) -> None:
        # Constructed lazily by the caller; reads ANTHROPIC_API_KEY from the
        # environment. We never hardcode a key.
        self._client = client or anthropic.Anthropic()

    def complete(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
        effort: str = "high",
    ) -> anthropic.types.Message:
        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": messages,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": effort},
        }
        # Only attach tools when the agent actually has some — an empty list is
        # a validation error, and a no-tool agent is a legitimate config.
        if tools:
            kwargs["tools"] = tools
        return self._client.messages.create(**kwargs)
