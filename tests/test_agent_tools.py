"""Claude's integration toolset: schemas, per-user execution, gating, the
orchestrator dispatch that lets the model call them, and the /agent/tools view.
"""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from backend.agent_tools import IntegrationTools, anthropic_schemas
from backend.api import create_app
from backend.crypto import TokenCipher
from backend.db import open_db
from backend.oauth import OAuthBroker
from backend.provider_api import ProviderAPI
from backend.repo import SessionRepo, TokenRepo, UserRepo


class _Resp:
    def __init__(self, payload, status=200):
        self._p, self.status_code = payload, status
    def json(self): return self._p


class _HTTP:
    def __init__(self, payload): self.payload = payload; self.calls = []
    def get(self, url, headers=None): self.calls.append(("GET", url)); return _Resp(self.payload)
    def post(self, url, headers=None, json=None): self.calls.append(("POST", url, json)); return _Resp({"html_url": "https://gh/acme/app/issues/3", "number": 3}, 201)


def _tools(payload=None):
    db = open_db("sqlite://:memory:")
    tokens = TokenRepo(db, TokenCipher())
    uid = UserRepo(db).create("t@x.com", "longenough1").id
    tokens.put(uid, "github", {"access_token": "AT", "expires_at": "2999-01-01T00:00:00+00:00"})
    api = ProviderAPI(OAuthBroker(tokens, state_secret="s"), http=_HTTP(payload or []))
    return IntegrationTools(api, uid), db


# ── registry ─────────────────────────────────────────────────────────────────
def test_schemas_are_anthropic_shaped():
    for s in anthropic_schemas():
        assert set(s) >= {"name", "description", "input_schema"}
        assert s["input_schema"]["type"] == "object"


def test_consequential_flags():
    tools, _ = _tools()
    assert tools.is_consequential("github_create_issue")
    assert not tools.is_consequential("github_list_repos")
    assert tools.is_tool("gmail_search") and not tools.is_tool("nope")


# ── execution (per-user tokens) ───────────────────────────────────────────────
def test_read_tool_executes_with_token():
    tools, _ = _tools(payload=[{"full_name": "acme/app", "private": False, "html_url": "u"}])
    out = tools.execute("github_list_repos", {"limit": 5})
    assert "acme/app" in out


def test_write_tool_executes():
    tools, _ = _tools()
    out = tools.execute("github_create_issue", {"repo": "acme/app", "title": "Fix"})
    assert '"number": 3' in out or "issues/3" in out


def test_execute_reports_not_connected():
    db = open_db("sqlite://:memory:")
    uid = UserRepo(db).create("n@x.com", "longenough1").id
    tools = IntegrationTools(ProviderAPI(OAuthBroker(TokenRepo(db, TokenCipher()), state_secret="s")), uid)
    assert "not connected" in tools.execute("github_list_repos", {})


# ── orchestrator dispatch: the model calls an integration tool ────────────────
class _Block:
    def __init__(self, **kw): self.__dict__.update(kw)


class _Msg:
    def __init__(self, content, stop_reason): self.content, self.stop_reason = content, stop_reason


class _Messages:
    def __init__(self, script): self.script = script; self.n = 0
    async def create(self, **_kw):
        m = self.script[min(self.n, len(self.script) - 1)]; self.n += 1; return m


class _LLM:
    def __init__(self, script): self.messages = _Messages(script)


class _Hermes:
    async def execute(self, task): return type("R", (), {"ok": True, "text": "hermes", "error": None})()
    async def health(self): return True


def _orch(llm):
    from gateway.config import load_settings
    from gateway.orchestrator import DonaldOrchestrator
    return DonaldOrchestrator(llm=llm, hermes=_Hermes(), settings=load_settings(),
                              personality_text="D")


def test_model_can_call_an_integration_tool():
    tools, _ = _tools(payload=[{"full_name": "acme/app", "private": False, "html_url": "u"}])
    from gateway.orchestrator import Session
    # Turn 1: model asks for github_list_repos. Turn 2: model answers.
    script = [
        _Msg([_Block(type="tool_use", id="t1", name="github_list_repos", input={"limit": 3})], "tool_use"),
        _Msg([_Block(type="text", text="You have 1 repo: acme/app.")], "end_turn"),
    ]
    orch = _orch(_LLM(script))
    sess = Session(session_id="s"); sess.tools = tools
    events = asyncio.run(_drain(orch, sess, "list my repos"))
    names = [e.get("name") for e in events if e["type"] in ("tool_call", "tool_result")]
    assert "github_list_repos" in names
    assert any(e["type"] == "final" and "acme/app" in e["text"] for e in events)


def test_consequential_tool_is_gated():
    tools, _ = _tools()
    from gateway.orchestrator import Session
    script = [
        _Msg([_Block(type="tool_use", id="t1", name="github_create_issue", input={"repo": "acme/app", "title": "X"})], "tool_use"),
        _Msg([_Block(type="text", text="Okay, cancelled.")], "end_turn"),
    ]
    orch = _orch(_LLM(script))

    async def deny(summary, reason): return False   # user says no
    orch.confirm_cb = deny
    sess = Session(session_id="s"); sess.tools = tools
    events = asyncio.run(_drain(orch, sess, "open an issue"))
    assert any(e["type"] == "tool_result" and e.get("declined") for e in events)


async def _drain(orch, sess, text):
    return [e async for e in orch.run_events(sess, text)]


# ── /agent/tools view ─────────────────────────────────────────────────────────
def test_agent_tools_endpoint_shows_readiness():
    db = open_db("sqlite://:memory:")
    uid = UserRepo(db).create("v@x.com", "longenough1").id
    TokenRepo(db, TokenCipher()).put(uid, "github", {"access_token": "AT"})
    client = TestClient(create_app(db=db))
    hdr = {"Authorization": f"Bearer {SessionRepo(db).issue(uid)}"}
    body = client.get("/agent/tools", headers=hdr).json()
    assert body["hermes"]["name"] == "hermes_execute"
    tools = {t["name"]: t for t in body["integrations"]}
    assert tools["github_list_repos"]["ready"] is True       # github connected
    assert tools["gmail_search"]["ready"] is False           # google not connected
    assert tools["github_create_issue"]["consequential"] is True
