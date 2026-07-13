"""Tier 3 ship test: the CC prompt renders all required sections; the subprocess
driver parses the NDJSON stream; generate_mockup verifies the build output."""

from __future__ import annotations

import json

from prism import bootstrap, prompts, tools
from prism import claude_code_runner as ccr


# ---------------------------------------------------------------------------
# CC -p prompt rendering
# ---------------------------------------------------------------------------


def _inputs(first_dispatch=True, refs=None, images=None):
    return prompts.CCPromptInputs(
        slug="acme",
        feature_slug="saas-landing",
        screen_name="hero",
        description="Design the marketing hero.",
        visual_direction="grid-pattern at 0.5 opacity layered with drifting particles.",
        quality="premium",
        first_dispatch=first_dispatch,
        expected_out_path="out/saas-landing/hero/index.html",
        page_path="app/saas-landing/hero/page.tsx",
        url_prefix="/api/acme/preview",
        components_hint=["border-beam", "particles"],
        reference_relpaths=refs or [],
        image_urls=images or [],
    )


def test_cc_prompt_has_all_required_sections():
    p = prompts.build_cc_prompt(_inputs())
    for needle in (
        "READ FIRST",
        "design.md",
        ".prism/brief.md",
        "features/saas-landing.md",
        "THE BRIEF IS LAW",
        "SCAFFOLD",
        "npm install",
        "COMPONENT PALETTE",
        "VISUAL ELEMENTS ARE REQUIRED",
        "VISUAL DIRECTION",
        "FORBIDDEN MOVES",
        "app/saas-landing/hero/page.tsx",
        "out/saas-landing/hero/index.html",
        "npm run build",
    ):
        assert needle in p, needle
    # heavy templating — the brief says this typically runs 4-6KB.
    assert len(p) > 2500


def test_cc_prompt_skips_install_when_not_first_dispatch():
    p = prompts.build_cc_prompt(_inputs(first_dispatch=False))
    assert "NOT the first dispatch" in p
    assert "Do NOT re-run `npm install`" in p


def test_cc_prompt_image_block_requires_all_urls():
    urls = [
        "/api/acme/preview/assets/saas-landing/backdrop.png",
        "/api/acme/preview/assets/saas-landing/product.png",
    ]
    p = prompts.build_cc_prompt(_inputs(images=urls))
    assert "exactly 2 `<img>` tag(s)" in p
    assert "Don't strip the basePath" in p or "don't auto-prefix" in p
    for u in urls:
        assert u in p


def test_system_prompt_carries_enforcement_sections():
    sp = prompts.system_prompt()
    assert "THE BRIEF IS LAW" in sp
    assert "VISUAL ELEMENTS ARE REQUIRED" in sp
    assert "FORBIDDEN" in sp  # font catalog forbidden list
    assert "magicui" in sp.lower()


# ---------------------------------------------------------------------------
# Subprocess driver: env sanitation, command build, stream parsing
# ---------------------------------------------------------------------------


def test_sanitize_env_drops_other_secrets():
    base = {
        "ANTHROPIC_API_KEY": "sk-ant", "PATH": "/usr/bin", "HOME": "/root",
        "SECRET_DB_PASSWORD": "nope", "GEMINI_API_KEY": "g",
    }
    env = ccr.sanitize_env(base)
    assert env["ANTHROPIC_API_KEY"] == "sk-ant"
    assert "SECRET_DB_PASSWORD" not in env
    assert "GEMINI_API_KEY" not in env  # not in the allowlist


def test_build_command_shape():
    cmd = ccr.build_command("hello", "claude-sonnet-4-6", 30, ["Read", "Write"])
    assert cmd[0] == "claude"
    assert "-p" in cmd and "hello" in cmd
    assert "--output-format" in cmd and "stream-json" in cmd
    assert "--allowedTools" in cmd and "Read,Write" in cmd


class _FakeStdout:
    def __init__(self, lines):
        self._lines = lines

    def __iter__(self):
        return iter(self._lines)


class _FakeStderr:
    def read(self):
        return ""


class _FakePopen:
    """Stands in for subprocess.Popen for the stream-parsing test."""

    def __init__(self, lines, returncode=0):
        self.stdout = _FakeStdout(lines)
        self.stderr = _FakeStderr()
        self.returncode = None
        self._rc = returncode

    def wait(self, timeout=None):
        self.returncode = self._rc
        return self._rc

    def kill(self):  # pragma: no cover - not hit in happy path
        self.returncode = -9


def test_spawn_parses_stream_and_collects_tool_uses():
    lines = [
        json.dumps({"type": "system", "subtype": "init"}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "design.md"}},
        ]}}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Write", "input": {"file_path": "app/x/hero/page.tsx"}},
        ]}}),
        json.dumps({"type": "result", "result": "done building"}),
        "",  # blank line should be ignored
    ]
    seen = []
    res = ccr.spawn_claude_code(
        "prompt", cwd="/tmp", model="claude-sonnet-4-6",
        on_event=seen.append,
        _popen=lambda *a, **k: _FakePopen(lines),
    )
    assert res.ok and res.returncode == 0
    assert res.result_text == "done building"
    names = [t["name"] for t in res.tool_uses]
    assert names == ["Read", "Write"]
    assert len(seen) == 4  # blank line dropped


# ---------------------------------------------------------------------------
# generate_mockup end-to-end with an injected spawn
# ---------------------------------------------------------------------------


def test_generate_mockup_verifies_build_output(project):
    slug, root = project
    bootstrap.bootstrap_project(slug)

    captured = {}

    def fake_spawn(prompt, cwd, model, max_turns, allowed_tools, on_event=None):
        captured["prompt"] = prompt
        captured["cwd"] = cwd
        # Simulate CC: write the page and the built static export.
        page = root / ".prism/preview/app/saas-landing/hero/page.tsx"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text('"use client";\nexport default function Hero(){return null}')
        out = root / ".prism/preview/out/saas-landing/hero/index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("<html></html>")
        return ccr.ClaudeCodeResult(ok=True, returncode=0,
                                    tool_uses=[{"name": "Write", "input": {}}])

    res = tools.execute_generate_mockup(
        slug, "saas-landing", "hero", "Design the hero.",
        visual_direction="grid-pattern at 0.5 opacity.",
        _spawn=fake_spawn,
    )
    assert res.ok is True
    assert res.view_url == "/api/test-app/preview/saas-landing/hero/"
    assert res.page_path == ".prism/preview/app/saas-landing/hero/page.tsx"
    assert "VISUAL ELEMENTS ARE REQUIRED" in captured["prompt"]
    assert str(captured["cwd"]).endswith(".prism/preview")


def test_generate_mockup_reports_missing_build(project):
    slug, root = project
    bootstrap.bootstrap_project(slug)

    def fake_spawn(prompt, cwd, model, max_turns, allowed_tools, on_event=None):
        return ccr.ClaudeCodeResult(ok=True, returncode=0)  # writes nothing

    res = tools.execute_generate_mockup(
        slug, "saas-landing", "hero", "Design the hero.", _spawn=fake_spawn,
    )
    assert res.ok is False
    assert "did not produce" in res.error
