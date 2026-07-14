"""Desktop auto-update delivery (M6). The Tauri updater polls a per-platform
endpoint; we answer 204 (you're current) or a JSON manifest pointing at the
signed artifact. The release pipeline writes a manifest file and uploads the
artifacts to object storage; this just serves the right entry for the caller's
platform and version.

Manifest shape (written on release):
    {
      "version": "0.1.1",
      "notes": "…",
      "pub_date": "2026-07-14T00:00:00Z",
      "platforms": {
        "linux-x86_64":   {"url": "https://cdn/…AppImage", "signature": "<.sig contents>"},
        "darwin-aarch64": {"url": "https://cdn/…app.tar.gz", "signature": "…"},
        "windows-x86_64": {"url": "https://cdn/…msi.zip", "signature": "…"}
      }
    }
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional


def _ver(s: Any) -> tuple:
    try:
        return tuple(int(x) for x in str(s).split(".")[:3])
    except (ValueError, TypeError):
        return (0,)


def load_manifest(path: str | None = None) -> Optional[dict]:
    path = path or os.getenv("UPDATE_MANIFEST_PATH")
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def resolve_update(
    manifest: Optional[dict], target: str, arch: str, current_version: str
) -> Optional[dict]:
    """The update to offer this caller, or None if it's already current / no build."""
    if not manifest:
        return None
    if _ver(manifest.get("version")) <= _ver(current_version):
        return None
    plat = (manifest.get("platforms") or {}).get(f"{target}-{arch}")
    if not plat or not plat.get("url") or not plat.get("signature"):
        return None
    return {
        "version": manifest["version"],
        "notes": manifest.get("notes", ""),
        "pub_date": manifest.get("pub_date"),
        "url": plat["url"],
        "signature": plat["signature"],
    }
