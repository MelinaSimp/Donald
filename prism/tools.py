"""Tier 3/5 — the agent's tools: schemas + execute branches.

Two tools are exposed to the planning agent:
  * ``generate_image``  — Tier 5; generate one image up front.
  * ``generate_mockup`` — Tier 3; compose one screen by spawning Claude Code.

The execute branches are plain functions (no SDK dependency) so they are unit
testable: ``spawn_claude_code`` is injectable, and ``generate_image`` accepts a
stub client.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from . import audit, config, docs, image_gen, prompts, references, scaffold
from . import claude_code_runner as ccr
from . import design_tokens as dt

# ---------------------------------------------------------------------------
# Tool schemas (Anthropic tool-use format)
# ---------------------------------------------------------------------------

GENERATE_MOCKUP_TOOL = {
    "name": "generate_mockup",
    "description": (
        "Compose a single high-fidelity screen by adding a Next.js page to the "
        "project's preview app and building it. Reads the design system + brief, "
        "scaffolds on first use, spawns Claude Code to write the TSX, and builds "
        "the static export. Call generate_image FIRST for any imagery, then pass "
        "the returned URLs verbatim inside visual_direction."
    ),
    "input_schema": {
        "type": "object",
        "required": ["feature_slug", "screen_name", "description"],
        "properties": {
            "feature_slug": {"type": "string"},
            "screen_name": {"type": "string"},
            "description": {"type": "string"},
            "visual_direction": {"type": "string"},
            "quality": {"type": "string", "enum": ["standard", "premium"]},
            "reference_images": {"type": "array", "items": {"type": "string"}},
            "components_hint": {"type": "array", "items": {"type": "string"}},
        },
    },
}

GENERATE_IMAGE_TOOL = {
    "name": "generate_image",
    "description": (
        "Generate one image (atmospheric backdrop, product render, or conceptual "
        "illustration) and save it into the preview app. Returns the FULL URL to "
        "drop verbatim into an <img> tag (basePath already baked in). Repeat the "
        "brief's palette in the prompt and name the forbidden colors to avoid the "
        "model's category defaults."
    ),
    "input_schema": {
        "type": "object",
        "required": ["feature_slug", "name", "prompt"],
        "properties": {
            "feature_slug": {"type": "string"},
            "name": {"type": "string", "description": "kebab-case asset name"},
            "prompt": {"type": "string"},
            "quality": {"type": "string", "enum": ["standard", "premium"]},
            "aspect_ratio": {"type": "string"},
        },
    },
}

ALL_TOOLS = [GENERATE_IMAGE_TOOL, GENERATE_MOCKUP_TOOL]


# ---------------------------------------------------------------------------
# Results
# ---------------------------------------------------------------------------


@dataclass
class MockupResult:
    ok: bool
    feature_slug: str
    screen_name: str
    page_path: str          # repo-relative path of the written page
    out_path: str           # absolute path that must exist after build
    view_url: str           # served URL of the screen
    scaffolded: bool        # True if the scaffold was created this dispatch
    first_dispatch: bool
    error: str = ""
    cc_returncode: int | None = None
    cc_tool_uses: list[dict] = field(default_factory=list)
    # Tier 6: audit the RENDERED TSX (install != use). Warnings are non-fatal.
    audit_passed: bool | None = None
    audit_warnings: list[str] = field(default_factory=list)


_ASSET_URL_RE_TMPL = r"{prefix}/assets/[^\s\"'()<>]+\.(?:png|jpe?g|webp)"


def _extract_image_urls(text: str, url_prefix: str) -> list[str]:
    pattern = re.compile(_ASSET_URL_RE_TMPL.format(prefix=re.escape(url_prefix)))
    seen: list[str] = []
    for m in pattern.finditer(text or ""):
        if m.group(0) not in seen:
            seen.append(m.group(0))
    return seen


# ---------------------------------------------------------------------------
# generate_image
# ---------------------------------------------------------------------------


def execute_generate_image(
    slug: str,
    feature_slug: str,
    name: str,
    prompt: str,
    *,
    quality: str = "standard",
    aspect_ratio: str | None = "16:9",
    _client=None,
) -> dict:
    """Execute branch for the generate_image tool. Returns a JSON-able dict."""
    res = image_gen.generate_image(
        slug, feature_slug, name, prompt,
        quality=quality, aspect_ratio=aspect_ratio, _client=_client,
    )
    return {
        "ok": True,
        "url": res.url,
        "model": res.model,
        "cost_usd": res.cost_usd,
        "note": "Use this exact URL verbatim in an <img> tag (basePath is baked in).",
    }


# ---------------------------------------------------------------------------
# generate_mockup
# ---------------------------------------------------------------------------


def execute_generate_mockup(
    slug: str,
    feature_slug: str,
    screen_name: str,
    description: str,
    *,
    visual_direction: str = "",
    quality: str = "standard",
    reference_images: list[str] | None = None,
    components_hint: list[str] | None = None,
    settings: config.Settings | None = None,
    on_event=None,
    _spawn=ccr.spawn_claude_code,
) -> MockupResult:
    """Execute branch for the generate_mockup tool."""
    settings = settings or config.Settings.from_env()
    feature_slug = docs.validate_slug(feature_slug, kind="feature_slug")
    screen_name = docs.validate_slug(screen_name, kind="screen_name")

    # 1/2. Parse design tokens — bail LOUDLY if the system is half-shaped.
    design_md = docs.read_project_file(slug, "design.md")
    tokens = dt.parse_tokens(design_md)  # raises TokenValidationError on bad input

    project_root = docs.resolve_project_root(slug)
    url_prefix = scaffold.default_url_prefix(slug)

    # 3. Scaffold-or-skip.
    scaffold_res = scaffold.prepare_scaffold(project_root, tokens, slug, url_prefix)
    preview_dir = scaffold_res.preview_dir

    # 5. Validate references (raises on traversal / wrong type / missing).
    references.resolve_references(slug, feature_slug, reference_images)
    ref_relpaths = list(reference_images or [])

    # First dispatch == node_modules not yet installed (npm install decision).
    first_dispatch = not (preview_dir / "node_modules").exists()

    page_rel = f"app/{feature_slug}/{screen_name}/page.tsx"
    out_rel = f"out/{feature_slug}/{screen_name}/index.html"
    image_urls = _extract_image_urls(visual_direction, url_prefix)

    cc_inputs = prompts.CCPromptInputs(
        slug=slug,
        feature_slug=feature_slug,
        screen_name=screen_name,
        description=description,
        visual_direction=visual_direction or description,
        quality=quality,
        first_dispatch=first_dispatch,
        expected_out_path=out_rel,
        page_path=page_rel,
        url_prefix=url_prefix,
        components_hint=list(components_hint or []),
        reference_relpaths=ref_relpaths,
        image_urls=image_urls,
    )
    cc_prompt = prompts.build_cc_prompt(cc_inputs)

    # 4/5. Spawn Claude Code in the preview app.
    cc = _spawn(
        cc_prompt,
        cwd=preview_dir,
        model=settings.composer_model,
        max_turns=settings.composer_max_turns,
        allowed_tools=ccr.DEFAULT_ALLOWED_TOOLS,
        on_event=on_event,
    )

    # 6. Verify the build actually produced the expected static export.
    out_abs = preview_dir / out_rel
    built = out_abs.exists()
    error = ""
    if not built:
        error = (
            f"build did not produce {out_rel}. "
            + (cc.error or "Claude Code finished without emitting the page.")
        )

    # Tier 6: audit the rendered TSX (not the install log) for required elements.
    audit_passed: bool | None = None
    audit_warnings: list[str] = []
    page_abs = preview_dir / page_rel
    if page_abs.exists():
        report = audit.audit_page_tsx(page_abs.read_text())
        audit_passed = report.passed
        audit_warnings = report.failures

    return MockupResult(
        ok=bool(built and cc.ok),
        feature_slug=feature_slug,
        screen_name=screen_name,
        page_path=f".prism/preview/{page_rel}",
        out_path=str(out_abs),
        view_url=f"{url_prefix}/{feature_slug}/{screen_name}/",
        scaffolded=not scaffold_res.skipped,
        first_dispatch=first_dispatch,
        error=error,
        cc_returncode=cc.returncode,
        cc_tool_uses=cc.tool_uses,
        audit_passed=audit_passed,
        audit_warnings=audit_warnings,
    )
