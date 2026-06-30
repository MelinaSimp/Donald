"""LLM client abstraction over the Anthropic Messages API.

Every LLM call in the Factory — research, prompt generation, and the
spawned ConfigDrivenAgents — goes through :class:`LLMClient`. The host's
existing Anthropic client is reused via :class:`AnthropicLLMClient`; tests
drive the whole pipeline with :class:`FakeLLMClient` so nothing burns tokens
or needs an API key.

:class:`LLMResponse` normalizes the response into Anthropic-style content
blocks (plain dicts) so the same loop code works for both clients and the
blocks can be fed straight back into the next ``messages`` turn.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol


@dataclass
class LLMResponse:
    stop_reason: str
    content: list[dict]  # Anthropic-style content blocks (text / tool_use)

    def text(self) -> str:
        return "".join(
            b.get("text", "") for b in self.content if b.get("type") == "text"
        ).strip()

    def tool_uses(self) -> list[dict]:
        return [b for b in self.content if b.get("type") == "tool_use"]


class LLMClient(Protocol):
    def create(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[dict] = None,
        max_tokens: int = 2048,
    ) -> LLMResponse: ...


class AnthropicLLMClient:
    """Thin wrapper over ``anthropic.Anthropic``.

    Pass an existing SDK client to reuse the host's configuration, or let it
    construct one from the environment (``ANTHROPIC_API_KEY``).
    """

    def __init__(self, *, api_key: Optional[str] = None, client: Any = None) -> None:
        if client is not None:
            self._client = client
        else:
            import anthropic  # imported lazily so tests need no key

            self._client = (
                anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
            )

    def create(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[dict] = None,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        kwargs: dict[str, Any] = {
            "model": model,
            "system": system,
            "messages": messages,
            "max_tokens": max_tokens,
        }
        if tools:
            kwargs["tools"] = tools
        if tool_choice:
            kwargs["tool_choice"] = tool_choice
        resp = self._client.messages.create(**kwargs)
        content = [self._block_to_dict(b) for b in resp.content]
        return LLMResponse(stop_reason=resp.stop_reason or "end_turn", content=content)

    @staticmethod
    def _block_to_dict(block: Any) -> dict:
        if isinstance(block, dict):
            return block
        if hasattr(block, "model_dump"):
            return block.model_dump(exclude_none=True)
        # Defensive fallback.
        return {"type": getattr(block, "type", "text"), "text": str(block)}


# Responder signature for the fake client.
Responder = Callable[..., "LLMResponse | dict"]


class FakeLLMClient:
    """Scriptable client for tests.

    ``responder`` is called with keyword args ``model, system, messages,
    tools, tool_choice`` and must return an :class:`LLMResponse` (or a dict
    with ``stop_reason`` and ``content``). Every call is recorded on
    ``.calls`` for assertions.
    """

    def __init__(self, responder: Responder) -> None:
        self._responder = responder
        self.calls: list[dict] = []

    def create(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        tool_choice: Optional[dict] = None,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        self.calls.append(
            {
                "model": model,
                "system": system,
                "messages": messages,
                "tools": tools,
                "tool_choice": tool_choice,
            }
        )
        out = self._responder(
            model=model,
            system=system,
            messages=messages,
            tools=tools,
            tool_choice=tool_choice,
        )
        if isinstance(out, LLMResponse):
            return out
        return LLMResponse(stop_reason=out["stop_reason"], content=out["content"])


# --- content-block helpers ------------------------------------------------- #


def text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def tool_use_block(tool_id: str, name: str, tool_input: dict) -> dict:
    return {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}
