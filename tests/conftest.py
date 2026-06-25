"""Shared fixtures: a throwaway project resolvable by Prism via PRISM_PROJECTS_BASE."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def project(tmp_path, monkeypatch):
    """Create a fresh project dir and make Prism resolve `<slug>` to it.

    Uses PRISM_PROJECTS_BASE convention so we never touch the real registry.
    Returns (slug, root_path).
    """
    base = tmp_path / "projects"
    base.mkdir()
    slug = "test-app"
    root = base / slug
    root.mkdir()
    # Minimal repo signal for the bootstrap scan.
    (root / "package.json").write_text(
        json.dumps({"name": slug, "description": "A test app for Prism.",
                    "dependencies": {"next": "15.0.0", "react": "19.0.0"}})
    )
    (root / "README.md").write_text("# Test App\n\nA delightful test application.\n")

    monkeypatch.setenv("PRISM_PROJECTS_BASE", str(base))
    monkeypatch.setenv("PRISM_REGISTRY", str(tmp_path / "no-registry.json"))
    return slug, root
