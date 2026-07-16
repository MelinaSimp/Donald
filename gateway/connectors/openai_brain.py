"""An OpenAI-compatible "brain" for Donald — so Claude isn't the only option.

The orchestrator was written to Anthropic's Messages API: it passes a two-block
``system`` list, an Anthropic-shaped ``messages`` history (with ``tool_use`` /
``tool_result`` blocks), and Anthropic-style ``tools``; and it reads back
``response.content`` blocks plus ``response.stop_reason``.

Plenty of providers (MiniMax, together, groq, local vLLM/Ollama, …) speak the
**OpenAI** chat-completions dialect instead. This adapter presents the exact
same ``.messages.create(...)`` surface the orchestrator expects, but underneath
it translates Anthropic⇄OpenAI both ways and calls an OpenAI-compatible
``/chat/completions`` endpoint. Nothing in the orchestrator changes.

Set it up with, e.g. (MiniMax):
    DONALD_PROVIDER=openai
    DONALD_BASE_URL=https://api.minimax.io/v1
    DONALD_API_KEY=<your MiniMax key>
    DONALD_MODEL=MiniMax-M2

The HTTP client is injectable so tests never hit the network.
"""

from __future__ import annotations

import json
import os
import re
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

# Reasoning models (MiniMax-M2, etc.) wrap their chain-of-thought in <think>…
# </think>. That's private scratch-work, not the answer — strip it before it
# reaches the user.
_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


def _strip_reasoning(text: str) -> str:
    if not text:
        return text
    cleaned = _THINK_BLOCK.sub("", text)
    # A dangling close tag (opening lost/streamed away): keep only what follows.
    if "</think>" in cleaned:
        cleaned = cleaned.rsplit("</think>", 1)[-1]
    # A dangling open tag (reasoning truncated, no answer yet): drop from it on.
    if "<think>" in cleaned:
        cleaned = cleaned.split("<think>", 1)[0]
    return cleaned.strip()


class OpenAICompatBrain:
    """Anthropic-shaped facade over an OpenAI-compatible chat API."""

    def __init__(
        self,
        base_url: str = "https://api.minimax.io/v1",
        api_key: Optional[str] = None,
        timeout_s: float = 120.0,
        client: Optional[object] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.timeout_s = timeout_s
        self._client = client
        # Mirror the Anthropic SDK surface the orchestrator calls: llm.messages.create(...)
        self.messages = _Messages(self)

    def _get_client(self):
        if self._client is None:
            import httpx  # imported lazily so the dep is only needed at runtime

            self._client = httpx.AsyncClient(timeout=self.timeout_s)
        return self._client

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        # OpenRouter uses these (optional) for app attribution / leaderboards.
        # Harmless with any other provider.
        referer = os.getenv("OPENROUTER_REFERER")
        title = os.getenv("OPENROUTER_TITLE")
        if referer:
            headers["HTTP-Referer"] = referer
        if title:
            headers["X-Title"] = title
        return headers

    async def _create(self, **kwargs) -> SimpleNamespace:
        payload = {
            "model": kwargs.get("model"),
            "messages": _to_openai_messages(
                kwargs.get("system"), kwargs.get("messages") or []
            ),
            "max_tokens": kwargs.get("max_tokens", 1024),
            "temperature": kwargs.get("temperature", 0.8),
            "stream": False,
        }
        tools = kwargs.get("tools")
        if tools:
            payload["tools"] = _tools_to_openai(tools)
            payload["tool_choice"] = "auto"

        client = self._get_client()
        resp = await client.post(
            f"{self.base_url}/chat/completions",
            headers=self._headers(),
            json=payload,
        )
        if getattr(resp, "status_code", 200) >= 400:
            body = _safe_text(resp)
            raise BrainError(
                f"brain (OpenAI-compatible) returned HTTP {resp.status_code}: {body}"
            )
        data = resp.json()
        return _from_openai_response(data)


class _Messages:
    def __init__(self, brain: OpenAICompatBrain) -> None:
        self._brain = brain

    async def create(self, **kwargs) -> SimpleNamespace:
        return await self._brain._create(**kwargs)


class BrainError(RuntimeError):
    """Raised when the OpenAI-compatible brain endpoint fails."""


# ---------------------------------------------------------------------------
# Anthropic -> OpenAI (request)
# ---------------------------------------------------------------------------
def _system_text(system: Any) -> str:
    """Flatten Anthropic's system (str or list of text blocks) to one string."""
    if not system:
        return ""
    if isinstance(system, str):
        return system
    parts: List[str] = []
    for block in system:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
        elif isinstance(block, str):
            parts.append(block)
    return "\n\n".join(p for p in parts if p)


def _to_openai_messages(system: Any, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    sys_text = _system_text(system)
    if sys_text:
        out.append({"role": "system", "content": sys_text})

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content")

        # Plain string content — the common case.
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue

        # Block-list content: split into text, tool_use (assistant) and
        # tool_result (-> OpenAI 'tool' messages).
        text_parts: List[str] = []
        tool_calls: List[Dict[str, Any]] = []
        tool_msgs: List[Dict[str, Any]] = []
        for block in content or []:
            btype = block.get("type") if isinstance(block, dict) else None
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id", ""),
                        "type": "function",
                        "function": {
                            "name": block.get("name", ""),
                            "arguments": json.dumps(block.get("input") or {}),
                        },
                    }
                )
            elif btype == "tool_result":
                tool_msgs.append(
                    {
                        "role": "tool",
                        "tool_call_id": block.get("tool_use_id", ""),
                        "content": _result_content_to_text(block.get("content")),
                    }
                )

        if role == "assistant" and (text_parts or tool_calls):
            assistant_msg: Dict[str, Any] = {
                "role": "assistant",
                "content": "".join(text_parts),
            }
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            out.append(assistant_msg)
        # tool_result blocks become standalone 'tool' messages (order preserved).
        out.extend(tool_msgs)

    return out


def _result_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return "" if content is None else str(content)


def _tools_to_openai(tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    converted = []
    for tool in tools:
        converted.append(
            {
                "type": "function",
                "function": {
                    "name": tool.get("name"),
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema", {"type": "object"}),
                },
            }
        )
    return converted


# ---------------------------------------------------------------------------
# OpenAI -> Anthropic (response)
# ---------------------------------------------------------------------------
def _from_openai_response(data: Dict[str, Any]) -> SimpleNamespace:
    choices = data.get("choices") or [{}]
    choice = choices[0] or {}
    message = choice.get("message") or {}

    blocks: List[SimpleNamespace] = []
    text = message.get("content")
    if isinstance(text, list):  # some providers return content as parts
        text = _result_content_to_text(text)
    text = _strip_reasoning(text) if text else text
    if text:
        blocks.append(SimpleNamespace(type="text", text=text))

    for tc in message.get("tool_calls") or []:
        fn = tc.get("function") or {}
        raw_args = fn.get("arguments") or "{}"
        try:
            args = json.loads(raw_args) if isinstance(raw_args, str) else (raw_args or {})
        except (ValueError, TypeError):
            args = {}
        blocks.append(
            SimpleNamespace(
                type="tool_use",
                id=tc.get("id", ""),
                name=fn.get("name", ""),
                input=args,
            )
        )

    finish = choice.get("finish_reason")
    stop_reason = "tool_use" if (finish == "tool_calls" or any(
        getattr(b, "type", None) == "tool_use" for b in blocks
    )) else "end_turn"

    return SimpleNamespace(content=blocks, stop_reason=stop_reason)


def _safe_text(resp) -> str:
    try:
        return resp.text[:300]
    except Exception:
        return "<unreadable body>"
