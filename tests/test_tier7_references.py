"""Tier 7 ship test: reference images are validated safely and instructed to be
read first; the CC prompt lists them; traversal/absolute/bad-type are rejected;
and CC's stream shows it Read the reference file."""

from __future__ import annotations

import json

import pytest

from prism import bootstrap, prompts, references, tools
from prism import claude_code_runner as ccr


def _drop_reference(root, feature_slug, name):
    ref = root / ".prism/references" / feature_slug / name
    ref.parent.mkdir(parents=True, exist_ok=True)
    ref.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    return ref


def test_valid_reference_resolves(project):
    slug, root = project
    bootstrap.bootstrap_project(slug)
    _drop_reference(root, "saas-landing", "linear-hero.png")
    paths = references.resolve_references(slug, "saas-landing", ["linear-hero.png"])
    assert len(paths) == 1 and paths[0].name == "linear-hero.png"


def test_traversal_rejected(project):
    slug, _ = project
    bootstrap.bootstrap_project(slug)
    with pytest.raises(references.ReferenceValidationError, match="\\.\\."):
        references.resolve_references(slug, "saas-landing", ["../../etc/passwd.png"])


def test_absolute_rejected(project):
    slug, _ = project
    bootstrap.bootstrap_project(slug)
    with pytest.raises(references.ReferenceValidationError, match="relative"):
        references.resolve_references(slug, "saas-landing", ["/etc/passwd.png"])


def test_bad_suffix_rejected(project):
    slug, _ = project
    bootstrap.bootstrap_project(slug)
    with pytest.raises(references.ReferenceValidationError):
        references.resolve_references(slug, "saas-landing", ["notes.txt"])


def test_missing_reference_rejected(project):
    slug, _ = project
    bootstrap.bootstrap_project(slug)
    with pytest.raises(references.ReferenceValidationError, match="not found"):
        references.resolve_references(slug, "saas-landing", ["nope.png"])


def test_cc_prompt_lists_references_read_first():
    inp = prompts.CCPromptInputs(
        slug="acme", feature_slug="saas-landing", screen_name="hero",
        description="d", visual_direction="v", quality="standard",
        first_dispatch=True,
        expected_out_path="out/saas-landing/hero/index.html",
        page_path="app/saas-landing/hero/page.tsx",
        url_prefix="/api/acme/preview",
        components_hint=[], reference_relpaths=["linear-hero.png", "stripe.png"],
        image_urls=[],
    )
    p = prompts.build_cc_prompt(inp)
    assert "READ THESE FIRST WITH THE Read TOOL" in p
    assert ".prism/references/saas-landing/linear-hero.png" in p
    assert ".prism/references/saas-landing/stripe.png" in p
    assert "OVERRIDE category defaults" in p


def test_dispatch_with_references_makes_cc_read_them(project):
    slug, root = project
    bootstrap.bootstrap_project(slug)
    _drop_reference(root, "saas-landing", "linear-hero.png")

    def fake_spawn(prompt, cwd, model, max_turns, allowed_tools, on_event=None):
        # Simulate CC reading the reference, then writing + building the page.
        events = [
            {"type": "assistant", "message": {"content": [
                {"type": "tool_use", "name": "Read",
                 "input": {"file_path": ".prism/references/saas-landing/linear-hero.png"}},
            ]}},
        ]
        result = ccr.ClaudeCodeResult(ok=True, returncode=0)
        for e in events:
            if on_event:
                on_event(e)
            result.tool_uses.extend(ccr._extract_tool_uses(e))
        page = root / ".prism/preview/app/saas-landing/hero/page.tsx"
        page.parent.mkdir(parents=True, exist_ok=True)
        page.write_text("export default function H(){return null}")
        out = root / ".prism/preview/out/saas-landing/hero/index.html"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("<html></html>")
        return result

    seen = []
    res = tools.execute_generate_mockup(
        slug, "saas-landing", "hero", "Design the hero.",
        visual_direction="anchored to linear-hero.png reference",
        reference_images=["linear-hero.png"],
        on_event=seen.append,
        _spawn=fake_spawn,
    )
    assert res.ok
    read_paths = [t["input"].get("file_path") for t in res.cc_tool_uses if t["name"] == "Read"]
    assert ".prism/references/saas-landing/linear-hero.png" in read_paths
