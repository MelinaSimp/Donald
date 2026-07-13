"""Tier 7 — reference images: the single biggest quality lever.

Users (or a future Scout-like agent) drop screenshots of reference designs into
``.prism/references/<feature_slug>/``. ``generate_mockup`` takes a
``reference_images`` arg listing paths *relative to that dir*; this module
validates them safely and resolves them to absolute paths CC can Read.

Critical alignment rule (Tier 7 stumbling block): the reference dir is keyed by
the *feature_slug the agent actually uses*, not the user's verbal phrasing. The
same slug flows through docs/image_gen/here so everything lines up.
"""

from __future__ import annotations

from pathlib import Path

from . import docs

ALLOWED_SUFFIXES = (".png", ".jpg", ".jpeg", ".webp")


class ReferenceValidationError(ValueError):
    """A reference image path was unsafe, wrong type, or missing."""


def _check_relpath(relpath: str) -> str:
    rp = (relpath or "").strip()
    if not rp:
        raise ReferenceValidationError("empty reference path.")
    if rp.startswith("/") or rp.startswith("\\"):
        raise ReferenceValidationError(f"reference '{rp}' must be relative, not absolute.")
    if ".." in Path(rp).parts:
        raise ReferenceValidationError(f"reference '{rp}' may not contain '..'.")
    if Path(rp).suffix.lower() not in ALLOWED_SUFFIXES:
        raise ReferenceValidationError(
            f"reference '{rp}' must be one of {ALLOWED_SUFFIXES}."
        )
    return rp


def resolve_reference(slug: str, feature_slug: str, relpath: str) -> Path:
    """Resolve one reference path under ``.prism/references/<feature_slug>/`` safely.

    Validates kebab-case slugs (via docs), bans traversal/absolute paths and
    disallowed suffixes, enforces project containment, and requires the file to
    exist.
    """
    rp = _check_relpath(relpath)
    ref_dir = docs.references_dir(slug, feature_slug)
    project_root = docs.resolve_project_root(slug)
    target = docs.assert_within_project(project_root, ref_dir / rp)
    if not target.exists():
        raise ReferenceValidationError(
            f"reference '{rp}' not found in {ref_dir} (looked for {target})."
        )
    return target


def resolve_references(
    slug: str, feature_slug: str, relpaths: list[str] | None
) -> list[Path]:
    """Validate + resolve a list of references. Raises on the first bad one."""
    if not relpaths:
        return []
    return [resolve_reference(slug, feature_slug, rp) for rp in relpaths]
