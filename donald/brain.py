"""The brain: whatever turns a conversation into Donald's next move.

A ``Brain`` takes the running message history (plus the available tool schemas)
and returns one ``BrainResponse``: either some text to say, or a set of tool
calls to execute, or both. The conversation loop (Tier 0) and the agent loop
(Tier 1) are written against this interface, so swapping the real Claude brain
for the offline mock — or for another model later — changes nothing upstream.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .config import Config


@dataclass
class ToolCall:
    id: str
    name: str
    input: dict[str, Any]


@dataclass
class BrainResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    # Raw assistant content blocks, so we can append them back to history
    # verbatim (required by the Anthropic tool-use protocol).
    raw_content: Any = None

    @property
    def wants_tools(self) -> bool:
        return bool(self.tool_calls)


class Brain:
    """Interface every brain implements."""

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> BrainResponse:
        raise NotImplementedError


# ──────────────────────────────────────────────────────────────────────────
# Real brain: Anthropic's Claude
# ──────────────────────────────────────────────────────────────────────────
class ClaudeBrain(Brain):
    def __init__(self, config: Config):
        from anthropic import Anthropic  # imported lazily so mock mode needs no SDK

        self.config = config
        self.client = Anthropic(api_key=config.anthropic_api_key)
        self.model = config.model

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> BrainResponse:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": 1024,
            "messages": messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = tools

        msg = self.client.messages.create(**kwargs)

        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        for block in msg.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, input=block.input or {})
                )

        return BrainResponse(
            text="".join(text_parts).strip(),
            tool_calls=tool_calls,
            raw_content=msg.content,
        )


# ──────────────────────────────────────────────────────────────────────────
# Mock brain: deterministic, offline, no API key. Lets you exercise the whole
# loop — including tool calls — before you ever spend a token.
# ──────────────────────────────────────────────────────────────────────────
class MockBrain(Brain):
    """A tiny rules-based stand-in for Claude.

    It is intentionally dumb but useful: it echoes, it can be steered to call a
    tool by saying things like "what time is it" or "remember that ...", and it
    always returns valid protocol-shaped responses so downstream code is tested
    for real.
    """

    def __init__(self, config: Config | None = None):
        self.config = config

    def complete(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        system: str | None = None,
    ) -> BrainResponse:
        last_user = self._last_user_text(messages)
        text = (last_user or "").lower()
        tool_names = {t["name"] for t in (tools or [])}

        # If the previous turn was a tool result, summarise it instead of
        # re-calling the tool (prevents infinite loops).
        if self._last_was_tool_result(messages):
            result_text = self._last_tool_result_text(messages)
            return BrainResponse(text=f"Done. {result_text}".strip())

        if "get_time" in tool_names and any(
            k in text for k in ("time", "date", "day is it")
        ):
            return self._call("get_time", {})

        if "remember" in tool_names and text.startswith(("remember", "note that", "save")):
            fact = last_user.split(" ", 1)[1] if " " in last_user else last_user
            return self._call("remember", {"content": fact})

        if "web_search" in tool_names and any(
            k in text for k in ("search", "look up", "what is", "who is")
        ):
            return self._call("web_search", {"query": last_user})

        if not last_user:
            return BrainResponse(text="Hi, I'm Donald. What can I do for you?")

        return BrainResponse(
            text=f"[mock] I heard: \"{last_user}\". "
            "Set ANTHROPIC_API_KEY and DONALD_BRAIN=claude for the real brain."
        )

    # -- helpers ----------------------------------------------------------
    def _call(self, name: str, args: dict[str, Any]) -> BrainResponse:
        call = ToolCall(id=f"mock_{name}", name=name, input=args)
        raw = [{"type": "tool_use", "id": call.id, "name": name, "input": args}]
        return BrainResponse(tool_calls=[call], raw_content=raw)

    @staticmethod
    def _last_user_text(messages: list[dict[str, Any]]) -> str:
        for m in reversed(messages):
            if m["role"] == "user":
                c = m["content"]
                if isinstance(c, str):
                    return c
                for block in c:
                    if isinstance(block, dict) and block.get("type") == "text":
                        return block["text"]
        return ""

    @staticmethod
    def _last_was_tool_result(messages: list[dict[str, Any]]) -> bool:
        if not messages:
            return False
        last = messages[-1]
        if last["role"] != "user" or isinstance(last["content"], str):
            return False
        return any(
            isinstance(b, dict) and b.get("type") == "tool_result"
            for b in last["content"]
        )

    @staticmethod
    def _last_tool_result_text(messages: list[dict[str, Any]]) -> str:
        last = messages[-1]
        for b in last["content"]:
            if isinstance(b, dict) and b.get("type") == "tool_result":
                content = b.get("content", "")
                if isinstance(content, list):
                    return " ".join(
                        x.get("text", "") for x in content if isinstance(x, dict)
                    )
                return str(content)
        return ""


def make_brain(config: Config) -> Brain:
    """Factory: hand back the brain the config asked for."""
    if config.brain == "claude":
        return ClaudeBrain(config)
    return MockBrain(config)
