"""Tier 2 ship test: scaffold writes 13 files; second call is skipped."""

from __future__ import annotations

from prism import bootstrap, scaffold


def test_scaffold_writes_13_files(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    res = scaffold.prepare_scaffold(root, bootstrap.DEFAULT_TOKENS, "test")
    assert not res.skipped
    assert len(res.files_written) == 13, res.files_written
    # spot-check the keystone files exist on disk
    preview = res.preview_dir
    for rel in ("package.json", "next.config.mjs", "app/layout.tsx",
                "app/globals.css", "lib/fonts.ts", "components.json",
                "prism/component_catalog.md"):
        assert (preview / rel).exists(), rel


def test_scaffold_is_idempotent(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    scaffold.prepare_scaffold(root, bootstrap.DEFAULT_TOKENS, "test")
    second = scaffold.prepare_scaffold(root, bootstrap.DEFAULT_TOKENS, "test")
    assert second.skipped is True
    assert second.files_written == []


def test_next_config_guards_stumbling_blocks(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    res = scaffold.prepare_scaffold(root, bootstrap.DEFAULT_TOKENS, "myapp")
    cfg = (res.preview_dir / "next.config.mjs").read_text()
    assert "output: 'export'" in cfg
    assert "trailingSlash: true" in cfg
    assert "basePath: '/api/myapp/preview'" in cfg
    assert "assetPrefix: '/api/myapp/preview'" in cfg
    assert "unoptimized: true" in cfg


def test_fonts_ts_uses_next_font_google(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    res = scaffold.prepare_scaffold(root, bootstrap.DEFAULT_TOKENS, "myapp")
    fonts_ts = (res.preview_dir / "lib/fonts.ts").read_text()
    assert 'from "next/font/google"' in fonts_ts
    assert "Fraunces" in fonts_ts and "Inter_Tight" in fonts_ts and "JetBrains_Mono" in fonts_ts
    assert "--font-display" in fonts_ts


def test_layout_applies_font_variables(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    res = scaffold.prepare_scaffold(root, bootstrap.DEFAULT_TOKENS, "myapp")
    layout = (res.preview_dir / "app/layout.tsx").read_text()
    assert "fontVariables" in layout and "dark" in layout


def test_globals_css_has_hsl_vars(tmp_path):
    root = tmp_path / "proj"
    root.mkdir()
    res = scaffold.prepare_scaffold(root, bootstrap.DEFAULT_TOKENS, "myapp")
    css = (res.preview_dir / "app/globals.css").read_text()
    assert "--background:" in css and "@tailwind base;" in css
