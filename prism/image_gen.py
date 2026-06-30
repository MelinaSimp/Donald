"""Tier 5 — AI image generation via Gemini.

Pure-TSX composition (waveforms, terminals, grids, particles) gets ~80% of the
way to a rich mockup. The last 20% needs real imagery: atmospheric backdrops,
product renders, conceptual illustrations. This module wraps the ``google-genai``
SDK to produce them.

Contract (each point guards a documented stumbling block):
  * saves the PNG under ``<project>/.prism/preview/public/assets/<feature>/<slug>.png``
    — Next copies ``public/*`` into ``out/`` at build time.
  * returns the FULL URL with the basePath baked in
    (``/api/<project>/preview/assets/<feature>/<slug>.png``) — NOT bare
    ``/assets/...``, because plain ``<img>`` tags don't get basePath auto-prefixed.
  * containment via ``assert_within_project``; slugs validated kebab-case.
  * aspect ratio is hinted via a prompt suffix (the v2 image+text models don't
    expose it as a param).
  * ``google.genai`` is imported lazily; absence is only fatal on the live path.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path

from . import config, docs
from . import scaffold as scaffold_mod


class ImageGenError(RuntimeError):
    pass


@dataclass
class ImageResult:
    url: str          # full URL with basePath, ready to drop into <img src=...>
    path: Path        # absolute path of the saved PNG
    model: str
    cost_usd: float


# Aspect-ratio hint suffixes (the image+text models don't take an aspect param).
_ASPECT_HINTS = {
    "16:9": "Composition: wide 16:9 cinematic framing.",
    "1:1": "Composition: square 1:1 framing.",
    "4:3": "Composition: 4:3 framing.",
    "3:2": "Composition: 3:2 framing.",
    "9:16": "Composition: tall 9:16 vertical framing.",
    "21:9": "Composition: ultrawide 21:9 cinematic framing.",
}


def _model_and_cost(quality: str) -> tuple[str, float]:
    if quality == "premium":
        return config.IMAGE_MODEL_PREMIUM, config.IMAGE_COST_PREMIUM_USD
    if quality == "standard":
        return config.IMAGE_MODEL_STANDARD, config.IMAGE_COST_STANDARD_USD
    raise ImageGenError(f"unknown quality '{quality}' (expected 'standard' or 'premium').")


def _build_prompt(prompt: str, aspect_ratio: str | None) -> str:
    if aspect_ratio and aspect_ratio in _ASPECT_HINTS:
        return f"{prompt.strip()}\n\n{_ASPECT_HINTS[aspect_ratio]}"
    return prompt.strip()


def _get_client():
    """Lazily construct a google-genai client from GEMINI_API_KEY."""
    key = config.gemini_api_key()
    if not key:
        raise ImageGenError(
            "GEMINI_API_KEY is not set. Image generation is unavailable. "
            "(Note: image-gen models require billing enabled — they are not in "
            "the free tier.)"
        )
    try:
        from google import genai  # type: ignore
    except ImportError as exc:  # pragma: no cover - depends on env
        raise ImageGenError(
            "google-genai is not installed. `pip install google-genai` to enable "
            "image generation."
        ) from exc
    return genai.Client(api_key=key)


def _extract_png_bytes(response) -> bytes:
    """Pull the first inline image payload out of a genai response."""
    candidates = getattr(response, "candidates", None) or []
    for cand in candidates:
        content = getattr(cand, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline = getattr(part, "inline_data", None)
            data = getattr(inline, "data", None) if inline is not None else None
            if data is None and isinstance(part, dict):
                inline = part.get("inline_data") or part.get("inlineData")
                data = (inline or {}).get("data")
            if data:
                if isinstance(data, (bytes, bytearray)):
                    return bytes(data)
                if isinstance(data, str):
                    return base64.b64decode(data)
    raise ImageGenError("genai response contained no inline image data.")


def asset_url(slug: str, feature_slug: str, name: str, url_prefix: str | None = None) -> str:
    url_prefix = url_prefix or scaffold_mod.default_url_prefix(slug)
    return f"{url_prefix}/assets/{feature_slug}/{name}.png"


def generate_image(
    slug: str,
    feature_slug: str,
    name: str,
    prompt: str,
    *,
    quality: str = "standard",
    aspect_ratio: str | None = "16:9",
    url_prefix: str | None = None,
    _client=None,  # injectable for tests
) -> ImageResult:
    """Generate one image and save it into the preview app's public/assets tree.

    Returns an ``ImageResult`` whose ``url`` is the full, basePath-prefixed URL
    to drop verbatim into a plain ``<img>`` tag.
    """
    docs.validate_slug(feature_slug, kind="feature_slug")
    name = docs.validate_slug(name, kind="image_name")
    model, cost = _model_and_cost(quality)

    project_root = docs.resolve_project_root(slug)
    rel = (
        Path(docs.PRISM_DIRNAME)
        / "preview" / "public" / "assets" / feature_slug / f"{name}.png"
    )
    target = docs.assert_within_project(project_root, rel)

    client = _client if _client is not None else _get_client()
    full_prompt = _build_prompt(prompt, aspect_ratio)
    try:
        response = client.models.generate_content(model=model, contents=full_prompt)
    except Exception as exc:  # noqa: BLE001 - surface a clean error to the agent
        raise ImageGenError(f"image generation failed ({model}): {exc}") from exc

    png = _extract_png_bytes(response)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(png)

    return ImageResult(
        url=asset_url(slug, feature_slug, name, url_prefix),
        path=target,
        model=model,
        cost_usd=cost,
    )
