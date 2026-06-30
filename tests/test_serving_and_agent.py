"""Serving path-resolution (the three routes + safety) and the agent tool router."""

from __future__ import annotations

import pytest

from prism import agent, docs, serving


# ---------------------------------------------------------------------------
# Serving
# ---------------------------------------------------------------------------


def _make_out(tmp_path):
    out = tmp_path / "out"
    (out / "_next" / "static").mkdir(parents=True)
    (out / "_next" / "static" / "app.js").write_text("console.log(1)")
    (out / "assets" / "voice").mkdir(parents=True)
    (out / "assets" / "voice" / "bg.png").write_bytes(b"\x89PNG")
    (out / "voice" / "hero").mkdir(parents=True)
    (out / "voice" / "hero" / "index.html").write_text("<html>hero</html>")
    (out / "index.html").write_text("<html>index</html>")
    return out


def test_resolve_next_asset(tmp_path):
    out = _make_out(tmp_path)
    p = serving.resolve_static(out, "_next/static/app.js")
    assert p.read_text() == "console.log(1)"


def test_resolve_generated_asset(tmp_path):
    out = _make_out(tmp_path)
    p = serving.resolve_static(out, "assets/voice/bg.png")
    assert p.read_bytes() == b"\x89PNG"


def test_resolve_screen_trailing_slash_to_index(tmp_path):
    out = _make_out(tmp_path)
    p = serving.resolve_static(out, "voice/hero/")
    assert "hero" in p.read_text()


def test_resolve_root_index(tmp_path):
    out = _make_out(tmp_path)
    assert "index" in serving.resolve_static(out, "").read_text()


def test_resolve_rejects_traversal(tmp_path):
    out = _make_out(tmp_path)
    (tmp_path / "secret.txt").write_text("nope")
    with pytest.raises(docs.PathContainmentError):
        serving.resolve_static(out, "../secret.txt")


def test_resolve_missing_raises_notfound(tmp_path):
    out = _make_out(tmp_path)
    with pytest.raises(serving.NotFound):
        serving.resolve_static(out, "voice/missing/")


def test_csp_allows_inline_script():
    # Next inlines a bootstrap script; without 'unsafe-inline' React won't hydrate.
    assert "script-src 'self' 'unsafe-inline'" in serving.CONTENT_SECURITY_POLICY


def test_content_type_guess():
    assert serving.guess_content_type(__import__("pathlib").Path("a.js")).endswith("javascript")
    assert "html" in serving.guess_content_type(__import__("pathlib").Path("a.html"))


# ---------------------------------------------------------------------------
# Agent tool router (no SDK / no network)
# ---------------------------------------------------------------------------


def test_dispatch_unknown_tool():
    out = agent.dispatch_tool_call("nope", {}, "slug")
    assert out["ok"] is False and "unknown tool" in out["error"]


def test_dispatch_image_error_is_returned_not_raised(project, monkeypatch):
    slug, _ = project
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    out = agent.dispatch_tool_call(
        "generate_image",
        {"feature_slug": "f", "name": "img", "prompt": "p"},
        slug,
    )
    assert out["ok"] is False
    assert "GEMINI_API_KEY" in out["error"]


def test_run_design_task_drives_tools_with_stub_client(project):
    """Drive the planning loop with a stub Anthropic client: one tool_use then stop."""
    slug, root = project
    from prism import bootstrap
    bootstrap.bootstrap_project(slug)

    class _Block(dict):
        __getattr__ = dict.get

    class _Resp:
        def __init__(self, content, stop):
            self.content = content
            self.stop_reason = stop

    class _StubMessages:
        def __init__(self):
            self.n = 0

        def create(self, **kw):
            self.n += 1
            if self.n == 1:
                return _Resp([
                    _Block(type="text", text="planning"),
                    _Block(type="tool_use", id="t1", name="generate_image",
                           input={"feature_slug": "f", "name": "bg", "prompt": "p"}),
                ], "tool_use")
            return _Resp([_Block(type="text", text="done")], "end_turn")

    class _StubClient:
        def __init__(self):
            self.messages = _StubMessages()

    res = agent.run_design_task(slug, "design the hero", _client=_StubClient())
    assert res.final_text == "done"
    assert len(res.tool_events) == 1
    assert res.tool_events[0].name == "generate_image"
    # generate_image failed (no key/stub) but the loop handled it gracefully.
    assert res.tool_events[0].output["ok"] is False
