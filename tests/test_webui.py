"""The web shell is served as static files and the root redirects to it."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from serve import mount_webui


def _client():
    return TestClient(mount_webui(FastAPI()), follow_redirects=False)


def test_root_redirects_to_app():
    r = _client().get("/")
    assert r.status_code in (307, 308)
    assert r.headers["location"] == "/app/"


def test_shell_html_is_served():
    r = _client().get("/app/")
    assert r.status_code == 200
    assert "DONALD_OS" in r.text
    assert "app.js" in r.text


def test_static_assets_served():
    c = _client()
    assert c.get("/app/app.js").status_code == 200
    assert c.get("/app/styles.css").status_code == 200
