"""Serve the static ``out/`` export of each project's preview app.

Routes, all under the per-project prefix ``/api/<slug>/preview``:
  * ``/_next/<path>``           -> out/_next/<path>
  * ``/assets/<path>``          -> out/assets/<path>      (Tier 5 images)
  * ``/<feature>/<screen>/``    -> out/<feature>/<screen>/index.html
  * ``/`` (index)               -> out/index.html

The path-resolution logic (``resolve_static``) is a pure function — containment
checked, traversal rejected — so it is unit testable without FastAPI. FastAPI is
imported lazily inside ``create_app`` so the package imports without it.

CSP must allow ``script-src 'self' 'unsafe-inline'`` — Next inlines a bootstrap
script and a strict no-script CSP silently breaks hydration.
"""

from __future__ import annotations

import mimetypes
from pathlib import Path

from . import docs

# Next inlines its bootstrap script; 'unsafe-inline' is required or React never
# hydrates. data: lets inlined fonts/images and Tier-5 PNGs load.
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; "
    "font-src 'self' data:; "
    "connect-src 'self'"
)


class NotFound(Exception):
    pass


def resolve_static(out_dir: Path, subpath: str) -> Path:
    """Map a request subpath (already stripped of the prefix) to a file in out/.

    Raises ``PathContainmentError`` on traversal, ``NotFound`` if the resolved
    file does not exist. A trailing-slash / empty path resolves to index.html
    (matching the trailingSlash:true export layout).
    """
    out_dir = Path(out_dir).resolve()
    sub = (subpath or "").lstrip("/")
    if sub == "" or sub.endswith("/"):
        sub = sub + "index.html"
    target = docs.assert_within_project(out_dir, Path(sub))
    if target.is_dir():
        target = target / "index.html"
    if not target.exists() or not target.is_file():
        raise NotFound(f"{subpath} -> {target} not found")
    return target


def guess_content_type(path: Path) -> str:
    ctype, _ = mimetypes.guess_type(str(path))
    return ctype or "application/octet-stream"


def preview_out_dir(slug: str) -> Path:
    """The out/ dir of a project's preview app."""
    return docs.preview_dir(slug) / "out"


def create_app(resolve_root=preview_out_dir):
    """Build a FastAPI app serving every project's preview export.

    ``resolve_root(slug) -> Path`` lets tests point at a temp out/ dir.
    FastAPI is imported here so the package imports without it installed.
    """
    try:
        from fastapi import FastAPI, Request, Response  # type: ignore
        from fastapi.responses import FileResponse  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on env
        raise RuntimeError(
            "fastapi is not installed. `pip install fastapi uvicorn` to serve "
            "mockups."
        ) from exc

    app = FastAPI(title="Prism preview server")

    @app.get("/api/{slug}/preview")
    @app.get("/api/{slug}/preview/{subpath:path}")
    def serve(slug: str, subpath: str = "", request: Request = None):  # noqa: ARG001
        try:
            docs.validate_slug(slug, kind="project_slug")
            out_dir = resolve_root(slug)
            target = resolve_static(out_dir, subpath)
        except docs.ProjectResolutionError:
            return Response(status_code=404)
        except docs.PathContainmentError:
            return Response(status_code=403)
        except NotFound:
            return Response(status_code=404)
        return FileResponse(
            target,
            media_type=guess_content_type(target),
            headers={"Content-Security-Policy": CONTENT_SECURITY_POLICY},
        )

    return app
