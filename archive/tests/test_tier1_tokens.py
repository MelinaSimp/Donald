"""Tier 1 ship test: tokens parse + bootstrap produces a parseable design.md."""

from __future__ import annotations

import pytest

from prism import bootstrap, design_tokens as dt, docs, fonts


def test_default_tokens_are_valid():
    dt.validate(bootstrap.DEFAULT_TOKENS)  # must not raise


def test_bootstrap_produces_parseable_design_md(project):
    slug, root = project
    result = bootstrap.bootstrap_project(slug)

    assert result.created_design and result.created_brief
    assert result.design_path.exists() and result.brief_path.exists()

    # The headline guarantee: design.md round-trips through the parser.
    text = docs.read_project_file(slug, "design.md")
    tokens = dt.parse_tokens(text)
    assert tokens.display_font == "Fraunces"
    assert tokens.colors["primary"] == "#f59e0b"
    assert tokens.base_color == "stone"
    assert tokens.style == "new-york"


def test_bootstrap_is_idempotent(project):
    slug, _ = project
    bootstrap.bootstrap_project(slug)
    second = bootstrap.bootstrap_project(slug)
    assert not second.created_design and not second.created_brief


def test_brief_commits_to_required_visual_elements(project):
    slug, _ = project
    bootstrap.bootstrap_project(slug)
    brief = docs.read_project_file(slug, ".prism/brief.md")
    assert "THE BRIEF IS LAW" in brief
    assert "Forbidden moves" in brief
    assert "violet + cyan" in brief
    assert "≥ 0.4" in brief


def test_missing_tokens_block_raises():
    with pytest.raises(dt.TokenValidationError):
        dt.parse_tokens("# design\n\nno token block here\n")


def test_forbidden_font_rejected():
    bad = dt.DesignTokens(
        fonts={"display": "Space Grotesk", "body": "Inter Tight", "mono": "JetBrains Mono"},
        colors={"background": "#000000", "foreground": "#ffffff",
                "primary": "#f59e0b", "accent": "#f59e0b"},
        radius="0.5rem", base_color="stone", style="new-york",
    )
    with pytest.raises(dt.TokenValidationError, match="forbidden"):
        dt.validate(bad)


def test_invalid_hex_rejected():
    bad = dt.DesignTokens(
        fonts={"display": "Fraunces", "body": "Inter Tight", "mono": "JetBrains Mono"},
        colors={"background": "not-a-hex", "foreground": "#ffffff",
                "primary": "#f59e0b", "accent": "#f59e0b"},
        radius="0.5rem", base_color="stone", style="new-york",
    )
    with pytest.raises(dt.TokenValidationError, match="not a valid hex"):
        dt.validate(bad)


def test_hex_to_hsl_roundtrip_known_values():
    # amber #f59e0b -> ~ (38, 92%, 50%)
    h, s, l = dt.hex_to_hsl("#f59e0b")
    assert 36 <= h <= 40
    assert 88 <= s <= 96
    assert 46 <= l <= 54
    # pure black / white anchors
    assert dt.hsl_var("#000000") == "0 0% 0%"
    assert dt.hsl_var("#ffffff") == "0 0% 100%"


def test_renderers_emit_expected_anchors():
    tokens = bootstrap.DEFAULT_TOKENS
    css = dt.render_globals_css(tokens)
    assert "--background:" in css and "@tailwind base;" in css
    twcfg = dt.render_tailwind_config(tokens)
    assert "var(--font-display)" in twcfg and "hsl(var(--primary))" in twcfg
    cj = dt.render_components_json(tokens)
    assert '"baseColor": "stone"' in cj and '"style": "new-york"' in cj


def test_font_catalog_excludes_forbidden():
    assert not (fonts.ALL_ALLOWED & fonts.FORBIDDEN_FAMILIES)
    assert fonts.is_allowed("Fraunces", "display")
    assert not fonts.is_allowed("Space Grotesk", "display")
