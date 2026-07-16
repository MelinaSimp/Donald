"""Filesystem access for the head-of-design agent's three-document model.

Every read/write is mediated here so that (a) project resolution goes through a
single ``slug -> filesystem_path`` registry and (b) nothing the agent writes can
escape its project root (``assert_within_project``). The agent never touches raw
paths; it speaks in slugs.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

# kebab-case, reused verbatim by image_gen and references so slugs line up
# everywhere (a reference dir must match the feature_slug — see Tier 7).
KEBAB_CASE_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

PRISM_DIRNAME = ".prism"


class ProjectResolutionError(ValueError):
    """The slug could not be mapped to a project root."""


class PathContainmentError(ValueError):
    """A target path escaped (or would escape) its project root."""


def validate_slug(slug: str, *, kind: str = "slug") -> str:
    slug = (slug or "").strip()
    if not KEBAB_CASE_RE.match(slug):
        raise ProjectResolutionError(
            f"invalid {kind} '{slug}': must be kebab-case ([a-z0-9] words joined by '-')."
        )
    return slug


# ---------------------------------------------------------------------------
# Project registry: slug -> filesystem path
# ---------------------------------------------------------------------------
#
# Resolution order:
#   1. explicit JSON registry file (PRISM_REGISTRY env, else <repo>/prism/registry.json)
#   2. convention: PRISM_PROJECTS_BASE/<slug> if that dir exists
# The registry maps slugs to absolute (or repo-relative) paths.


def _repo_root() -> Path:
    # prism/ lives at the repo root in this codebase.
    return Path(__file__).resolve().parent.parent


def _registry_path() -> Path:
    env = os.environ.get("PRISM_REGISTRY")
    if env:
        return Path(env).expanduser().resolve()
    return _repo_root() / "prism" / "registry.json"


def load_registry() -> dict[str, str]:
    path = _registry_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ProjectResolutionError(f"registry {path} is not valid JSON: {exc}") from exc
    projects = data.get("projects", data) if isinstance(data, dict) else {}
    if not isinstance(projects, dict):
        raise ProjectResolutionError(f"registry {path} must map slugs to paths.")
    return {str(k): str(v) for k, v in projects.items()}


def register_project(slug: str, path: str | Path) -> None:
    """Add/update a slug -> path mapping in the registry file (creates it if absent)."""
    slug = validate_slug(slug, kind="project_slug")
    reg_path = _registry_path()
    existing: dict = {}
    if reg_path.exists():
        existing = json.loads(reg_path.read_text())
        if "projects" not in existing:
            existing = {"projects": existing}
    else:
        existing = {"projects": {}}
    existing.setdefault("projects", {})[slug] = str(Path(path).resolve())
    reg_path.parent.mkdir(parents=True, exist_ok=True)
    reg_path.write_text(json.dumps(existing, indent=2) + "\n")


def resolve_project_root(slug: str) -> Path:
    slug = validate_slug(slug, kind="project_slug")
    registry = load_registry()
    if slug in registry:
        root = Path(registry[slug]).expanduser()
        if not root.is_absolute():
            root = (_repo_root() / root).resolve()
        else:
            root = root.resolve()
        if not root.exists():
            raise ProjectResolutionError(
                f"project '{slug}' maps to {root}, which does not exist."
            )
        return root

    base = os.environ.get("PRISM_PROJECTS_BASE")
    if base:
        candidate = (Path(base).expanduser() / slug).resolve()
        if candidate.exists():
            return candidate

    raise ProjectResolutionError(
        f"project '{slug}' is not in the registry ({_registry_path()}) and no "
        f"PRISM_PROJECTS_BASE/<slug> directory exists. Register it with "
        f"prism.docs.register_project('{slug}', '/path/to/project')."
    )


# ---------------------------------------------------------------------------
# Containment
# ---------------------------------------------------------------------------


def assert_within_project(project_root: Path, target: Path) -> Path:
    """Return the resolved target path, or raise if it escapes ``project_root``.

    Works for not-yet-existing targets (resolves the lexical path, not symlinks
    of the leaf). The check is parent-anchored so a path can be created safely.
    """
    project_root = project_root.resolve()
    # Resolve against the (existing) project root without requiring target to exist.
    candidate = (project_root / target).resolve() if not target.is_absolute() else target.resolve()
    if candidate != project_root and project_root not in candidate.parents:
        raise PathContainmentError(
            f"path {candidate} escapes project root {project_root}."
        )
    return candidate


# ---------------------------------------------------------------------------
# Path helpers for the three-document model
# ---------------------------------------------------------------------------


def prism_dir(slug: str) -> Path:
    return resolve_project_root(slug) / PRISM_DIRNAME


def design_doc_path(slug: str) -> Path:
    return resolve_project_root(slug) / "design.md"


def brief_path(slug: str) -> Path:
    return prism_dir(slug) / "brief.md"


def feature_doc_path(slug: str, feature_slug: str) -> Path:
    feature_slug = validate_slug(feature_slug, kind="feature_slug")
    return resolve_project_root(slug) / "features" / f"{feature_slug}.md"


def references_dir(slug: str, feature_slug: str) -> Path:
    feature_slug = validate_slug(feature_slug, kind="feature_slug")
    return prism_dir(slug) / "references" / feature_slug


def preview_dir(slug: str) -> Path:
    return prism_dir(slug) / "preview"


# ---------------------------------------------------------------------------
# Read / write
# ---------------------------------------------------------------------------


def read_project_file(slug: str, relpath: str) -> str:
    root = resolve_project_root(slug)
    target = assert_within_project(root, Path(relpath))
    if not target.exists():
        raise FileNotFoundError(f"{relpath} not found in project '{slug}'.")
    return target.read_text()


def list_project_files(slug: str, pattern: str = "**/*") -> list[str]:
    root = resolve_project_root(slug)
    return sorted(
        str(p.relative_to(root))
        for p in root.glob(pattern)
        if p.is_file()
    )


def _write(target: Path, content: str) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return target


def write_design_doc(slug: str, content: str) -> Path:
    root = resolve_project_root(slug)
    return _write(assert_within_project(root, Path("design.md")), content)


def write_brief(slug: str, content: str) -> Path:
    root = resolve_project_root(slug)
    return _write(assert_within_project(root, Path(PRISM_DIRNAME) / "brief.md"), content)


def write_feature_doc(slug: str, feature_slug: str, content: str) -> Path:
    feature_slug = validate_slug(feature_slug, kind="feature_slug")
    root = resolve_project_root(slug)
    rel = Path("features") / f"{feature_slug}.md"
    return _write(assert_within_project(root, rel), content)
