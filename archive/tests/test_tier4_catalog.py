"""Tier 4 ship test: catalog renders for prompt + full markdown without throwing."""

from __future__ import annotations

from prism import component_catalog as cc


def test_render_for_prompt():
    out = cc.render_for_prompt()
    assert "npx shadcn@latest add" in out
    assert "npx magicui-cli add" in out
    assert "grid-pattern" in out and "border-beam" in out
    # copy-paste-only libs must be flagged as NOT installable
    assert "do NOT npx these" in out


def test_render_full_markdown():
    md = cc.render_full_catalog_markdown()
    assert md.startswith("# Component Catalog")
    assert "Installing a component is not using it" in md
    assert "framer-motion" in md


def test_snapshot_only_have_no_install_command():
    assert all(e.install == "" for e in cc.SNAPSHOT_ONLY)


def test_installable_entries_have_commands():
    for e in (*cc.SHADCN_COMPONENTS, *cc.MAGICUI_COMPONENTS):
        assert e.install and ("shadcn" in e.install or "magicui-cli" in e.install)
