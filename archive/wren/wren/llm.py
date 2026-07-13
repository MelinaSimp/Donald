"""The provider seam.

Everything that talks to the model goes through here and nowhere else. This is
what lets us swap models, add retries, and track cost in one place (Tier 1). The
rest of the harness depends on the small `LLM` protocol below, never on the
Anthropic SDK directly — which is also what makes the brain testable without an
API key (tests pass in a fake LLM).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol

# Per-model output token pricing ($ / 1M tokens) for the running cost tally
# (Tier 6). Input is the first number, output the second.
_PRICING = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class Turn:
    """The result of one model turn."""

    content: list[Any]               # raw assistant blocks, appended to history verbatim
    text: str                        # concatenated text blocks
    tool_calls: list[ToolCall]
    stop_reason: str | None
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0

    @property
    def wants_tools(self) -> bool:
        return self.stop_reason == "tool_use"


class LLM(Protocol):
    """The seam. The agent depends only on this."""

    def stream_turn(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        on_text: Callable[[str], None] | None = None,
    ) -> Turn:
        ...


@dataclass
class AnthropicLLM:
    """The real brain — Claude via the official SDK, streaming."""

    model: str = "claude-opus-4-8"
    max_tokens: int = 1024
    thinking: str = "off"            # "off" | "adaptive"
    effort: str = "medium"
    api_key: str | None = None
    max_retries: int = 3
    _client: Any = field(default=None, repr=False)

    def _client_lazy(self):
        if self._client is None:
            import anthropic  # imported lazily so the package loads without it

            if not self.api_key:
                raise RuntimeError(
                    "Missing ANTHROPIC_API_KEY. Copy .env.example to .env and set it."
                )
            self._client = anthropic.Anthropic(api_key=self.api_key)
        return self._client

    def _request_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"model": self.model, "max_tokens": self.max_tokens}
        if str(self.thinking).lower() == "adaptive":
            # Adaptive thinking + effort (Opus 4.8 surface). Off by default for
            # latency; the persona keeps replies brief without it.
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": self.effort}
        return kwargs

    def stream_turn(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        on_text: Callable[[str], None] | None = None,
    ) -> Turn:
        import anthropic

        kwargs = self._request_kwargs()
        kwargs["system"] = system
        kwargs["messages"] = messages
        if tools:
            kwargs["tools"] = tools

        last_err: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                return self._stream_once(kwargs, on_text)
            except (anthropic.APIConnectionError, anthropic.RateLimitError,
                    anthropic.InternalServerError) as e:
                # Network/overload — back off and retry. A daily-driver
                # assistant has to shrug these off rather than crash (Tier 1).
                last_err = e
                time.sleep(2 ** attempt)
        raise RuntimeError(f"Model unreachable after {self.max_retries} tries: {last_err}")

    def _stream_once(self, kwargs: dict[str, Any], on_text):
        client = self._client_lazy()
        with client.messages.stream(**kwargs) as stream:
            for event in stream:
                if (
                    on_text
                    and event.type == "content_block_delta"
                    and event.delta.type == "text_delta"
                ):
                    on_text(event.delta.text)
            msg = stream.get_final_message()
        return self._to_turn(msg)

    def _to_turn(self, msg) -> Turn:
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in msg.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(block.id, block.name, dict(block.input)))
        cin, cout = _PRICING.get(self.model, (0.0, 0.0))
        usage = msg.usage
        cost = (usage.input_tokens * cin + usage.output_tokens * cout) / 1_000_000
        return Turn(
            content=msg.content,
            text="".join(text_parts),
            tool_calls=tool_calls,
            stop_reason=msg.stop_reason,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost_usd=cost,
        )


def build_llm(config) -> AnthropicLLM:
    """Construct the real LLM from config + secrets."""
    return AnthropicLLM(
        model=config.get("brain.model", "claude-opus-4-8"),
        max_tokens=config.get("brain.max_tokens", 1024),
        thinking=config.get("brain.thinking", "off"),
        effort=config.get("brain.effort", "medium"),
        # Not required at construction — only when Wren actually talks. Keeps
        # keyless commands (inbox, heartbeat, kill, cost) working without a key.
        api_key=config.secret("ANTHROPIC_API_KEY", required=False),
    )
