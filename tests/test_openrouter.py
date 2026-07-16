"""The OpenAI-compatible brain works against OpenRouter: right endpoint, auth,
optional attribution headers, tool-calling round-trip — all without the network.
"""

from __future__ import annotations

import asyncio

from gateway.connectors.openai_brain import OpenAICompatBrain


class _Resp:
    def __init__(self, payload): self._p = payload; self.status_code = 200
    def json(self): return self._p


class _FakeClient:
    def __init__(self, payload): self.payload = payload; self.posts = []
    async def post(self, url, headers=None, json=None):
        self.posts.append({"url": url, "headers": headers, "json": json})
        return _Resp(self.payload)


def _run(coro): return asyncio.run(coro)


def test_openrouter_request_shape(monkeypatch):
    monkeypatch.setenv("OPENROUTER_REFERER", "https://donald.example")
    monkeypatch.setenv("OPENROUTER_TITLE", "Donald OS")
    client = _FakeClient({"choices": [{"message": {"content": "hi from openrouter"}, "finish_reason": "stop"}]})
    brain = OpenAICompatBrain(base_url="https://openrouter.ai/api/v1", api_key="sk-or-x", client=client)

    resp = _run(brain.messages.create(
        model="anthropic/claude-sonnet-4",
        system="You are Donald.",
        messages=[{"role": "user", "content": "hello"}],
        max_tokens=64, temperature=0.5,
    ))
    post = client.posts[0]
    assert post["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert post["headers"]["Authorization"] == "Bearer sk-or-x"
    assert post["headers"]["HTTP-Referer"] == "https://donald.example"
    assert post["headers"]["X-Title"] == "Donald OS"
    assert post["json"]["model"] == "anthropic/claude-sonnet-4"
    assert post["json"]["messages"][0] == {"role": "system", "content": "You are Donald."}
    # Response comes back in the Anthropic shape the orchestrator reads.
    assert resp.content[0].text == "hi from openrouter" and resp.stop_reason == "end_turn"


def test_openrouter_tool_call_roundtrip():
    client = _FakeClient({"choices": [{"message": {"content": "", "tool_calls": [
        {"id": "call_1", "type": "function",
         "function": {"name": "hermes_execute", "arguments": "{\"task\": \"ls\"}"}}]},
        "finish_reason": "tool_calls"}]})
    brain = OpenAICompatBrain(base_url="https://openrouter.ai/api/v1", api_key="k", client=client)
    resp = _run(brain.messages.create(
        model="m", system="s", messages=[{"role": "user", "content": "list files"}],
        tools=[{"name": "hermes_execute", "description": "run", "input_schema": {"type": "object"}}],
    ))
    # tools were sent OpenAI-shaped; the tool call is read back Anthropic-shaped.
    assert client.posts[0]["json"]["tools"][0]["type"] == "function"
    assert resp.stop_reason == "tool_use"
    assert resp.content[0].name == "hermes_execute" and resp.content[0].input == {"task": "ls"}
