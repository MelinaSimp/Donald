"""Tier 5 ship test: a stubbed genai client saves a PNG and returns the full URL
(with basePath baked in, NOT a bare /assets path)."""

from __future__ import annotations

import pytest

from prism import image_gen


class _Inline:
    def __init__(self, data):
        self.inline_data = type("I", (), {"data": data})()


class _Content:
    def __init__(self, parts):
        self.parts = parts


class _Cand:
    def __init__(self, parts):
        self.content = _Content(parts)


class _Resp:
    def __init__(self, parts):
        self.candidates = [_Cand(parts)]


class _StubModels:
    def __init__(self, png):
        self._png = png
        self.calls = []

    def generate_content(self, model, contents):
        self.calls.append({"model": model, "contents": contents})
        return _Resp([_Inline(self._png)])


class _StubClient:
    def __init__(self, png):
        self.models = _StubModels(png)


_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16  # not a real image, just bytes to save


def test_generate_image_saves_png_and_returns_full_url(project):
    slug, root = project
    stub = _StubClient(_PNG)

    res = image_gen.generate_image(
        slug, "saas-landing", "atmospheric-backdrop",
        "near-black and amber, NO violet, NO cyan",
        quality="standard", aspect_ratio="16:9", _client=stub,
    )

    # Full URL with basePath baked in — never a bare /assets path.
    assert res.url == "/api/test-app/preview/assets/saas-landing/atmospheric-backdrop.png"
    assert not res.url.startswith("/assets/")
    assert res.model == image_gen.config.IMAGE_MODEL_STANDARD
    assert res.cost_usd == pytest.approx(0.04)

    # PNG saved under the preview app's public/assets tree.
    expected = root / ".prism/preview/public/assets/saas-landing/atmospheric-backdrop.png"
    assert res.path == expected
    assert expected.read_bytes() == _PNG

    # aspect-ratio hint is appended to the prompt sent to the model.
    assert "16:9" in stub.models.calls[0]["contents"]


def test_premium_uses_preview_model(project):
    slug, _ = project
    stub = _StubClient(_PNG)
    res = image_gen.generate_image(
        slug, "f", "img", "prompt", quality="premium", _client=stub,
    )
    assert res.model == image_gen.config.IMAGE_MODEL_PREMIUM
    assert res.cost_usd == pytest.approx(0.12)


def test_bad_image_name_rejected(project):
    slug, _ = project
    stub = _StubClient(_PNG)
    with pytest.raises(Exception):
        image_gen.generate_image(slug, "f", "Bad Name!", "p", _client=stub)


def test_missing_key_raises_clean_error(project, monkeypatch):
    slug, _ = project
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    # No _client injected and no key -> a clear ImageGenError, not an ImportError.
    with pytest.raises(image_gen.ImageGenError, match="GEMINI_API_KEY"):
        image_gen.generate_image(slug, "f", "img", "p")
