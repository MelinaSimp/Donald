"""Desktop update endpoint: 204 when current, a signed manifest when newer."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from backend.api import create_app
from backend.db import open_db
from backend.updates import resolve_update

MANIFEST = {
    "version": "0.2.0",
    "notes": "Faster orb.",
    "pub_date": "2026-07-14T00:00:00Z",
    "platforms": {
        "linux-x86_64": {"url": "https://cdn/donald_0.2.0_amd64.AppImage", "signature": "SIG"},
    },
}


def test_resolve_offers_newer_only():
    assert resolve_update(MANIFEST, "linux", "x86_64", "0.1.0")["version"] == "0.2.0"
    assert resolve_update(MANIFEST, "linux", "x86_64", "0.2.0") is None   # same
    assert resolve_update(MANIFEST, "linux", "x86_64", "0.3.0") is None   # newer client
    assert resolve_update(MANIFEST, "windows", "x86_64", "0.1.0") is None  # no build
    assert resolve_update(None, "linux", "x86_64", "0.1.0") is None        # no manifest


def test_endpoint_204_without_manifest():
    client = TestClient(create_app(db=open_db("sqlite://:memory:")))
    assert client.get("/api/update/linux/x86_64/0.1.0").status_code == 204


def test_endpoint_serves_manifest(tmp_path, monkeypatch):
    mf = tmp_path / "latest.json"
    mf.write_text(json.dumps(MANIFEST))
    monkeypatch.setenv("UPDATE_MANIFEST_PATH", str(mf))
    client = TestClient(create_app(db=open_db("sqlite://:memory:")))
    r = client.get("/api/update/linux/x86_64/0.1.0")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "0.2.0" and body["signature"] == "SIG"
    assert body["url"].endswith(".AppImage")
    # A current client gets 204.
    assert client.get("/api/update/linux/x86_64/0.2.0").status_code == 204
