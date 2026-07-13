"""Bootstrap a project's design system on first dispatch.

The cardinal rule (Tier 1): the generated design.md and brief.md must commit to
*concrete* values — specific fonts, specific hex, specific forbidden moves — not
TODO placeholders. A skeleton system produces skeleton mockups. The user
iterates from a real starting point, not a blank one.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from . import design_tokens as dt
from . import docs

# ---------------------------------------------------------------------------
# Concrete defaults — an award-winning dark editorial system with one amber accent.
# Deliberately opinionated; chosen to pass validation and to look like something.
# ---------------------------------------------------------------------------

DEFAULT_TOKENS = dt.DesignTokens(
    fonts={
        "display": "Fraunces",
        "body": "Inter Tight",
        "mono": "JetBrains Mono",
    },
    colors={
        "background": "#0a0a0b",
        "foreground": "#f5f5f4",
        "primary": "#f59e0b",   # amber 500
        "accent": "#f59e0b",
        "muted": "#1c1c1f",
        "card": "#101012",
        "border": "#27272a",
        "secondary": "#1c1c1f",
        "destructive": "#ef4444",
        "ring": "#f59e0b",
    },
    radius="0.625rem",
    base_color="stone",
    style="new-york",
)


@dataclass
class RepoScan:
    project_name: str
    description: str
    has_package_json: bool
    dependencies: list[str]
    css_files: list[str]
    readme_excerpt: str


# ---------------------------------------------------------------------------
# Repo scan
# ---------------------------------------------------------------------------


def scan_repo(root: Path) -> RepoScan:
    root = Path(root)
    name = root.name
    description = ""
    deps: list[str] = []
    has_pkg = False

    pkg = root / "package.json"
    if pkg.exists():
        has_pkg = True
        try:
            data = json.loads(pkg.read_text())
            name = data.get("name", name) or name
            description = data.get("description", "") or ""
            deps = sorted({*(data.get("dependencies") or {}), *(data.get("devDependencies") or {})})
        except (json.JSONDecodeError, OSError):
            pass

    readme_excerpt = ""
    for candidate in ("README.md", "Readme.md", "readme.md"):
        rp = root / candidate
        if rp.exists():
            text = rp.read_text(errors="ignore").strip()
            # First non-heading paragraph, lightly cleaned.
            for block in re.split(r"\n\s*\n", text):
                cleaned = block.strip().lstrip("#").strip()
                if cleaned and not cleaned.lower().startswith("project repository"):
                    readme_excerpt = cleaned[:400]
                    break
            if not description:
                description = readme_excerpt
            break

    css_files = sorted(
        str(p.relative_to(root))
        for p in root.glob("**/*.css")
        if "node_modules" not in p.parts and ".prism" not in p.parts
    )[:10]

    if not description:
        description = f"{name} — design system bootstrapped by Prism."

    return RepoScan(
        project_name=name,
        description=description,
        has_package_json=has_pkg,
        dependencies=deps,
        css_files=css_files,
        readme_excerpt=readme_excerpt,
    )


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def _tokens_yaml_block(tokens: dt.DesignTokens) -> str:
    colors_lines = "\n".join(f'  {k}: "{v}"' for k, v in tokens.colors.items())
    return f"""```yaml tokens
fonts:
  display: "{tokens.display_font}"
  body: "{tokens.body_font}"
  mono: "{tokens.mono_font}"
colors:
{colors_lines}
radius: "{tokens.radius}"
shadcn:
  base_color: "{tokens.base_color}"
  style: "{tokens.style}"
```"""


def render_design_md(scan: RepoScan, tokens: dt.DesignTokens = DEFAULT_TOKENS) -> str:
    return f"""# Design System — {scan.project_name}

> PUBLIC, STABLE. This is the design system of record. The fenced
> `yaml tokens` block below is the machine-readable source of truth — Prism
> parses it to render Tailwind, globals.css, shadcn config and font wiring.
> Edit values here; everything downstream re-renders.

{_tokens_yaml_block(tokens)}

## Typography

- **Display — {tokens.display_font}.** Used at 96–140px for editorial wordmarks
  with hand-tuned tracking and tight leading. The voice of the brand.
- **Body — {tokens.body_font}.** Calm, neutral, deliberate at reading sizes.
- **Mono — {tokens.mono_font}.** Marginalia, status readouts, labels. Sized
  14–16px so it is *seen*, never 11px noise.

## Color

Near-black canvas (`{tokens.colors['background']}`) under warm off-white text
(`{tokens.colors['foreground']}`). A **single** accent — amber
`{tokens.colors['primary']}` — used with precision: hairline borders, beams,
carets, status pulses. Never as decorative fills, never two accents at once.

## Radius & surface

Radius `{tokens.radius}`. Surfaces are layered, low-contrast cards
(`{tokens.colors['card']}`) over the canvas with `{tokens.colors['border']}`
hairlines, not heavy elevation shadows.

## Motion (system level)

Motion is continuous and ambient, not one-shot on load. Texture drift, breathing
pulses, number tickers, blinking carets. See the brief's visual-elements
contract for the non-negotiables.
"""


def render_brief_md(scan: RepoScan) -> str:
    """The private, evolving strategic memory — committed to award-winning specifics."""
    return f"""# Brief — {scan.project_name}

> PRIVATE, EVOLVING. Strategic memory for the head-of-design agent.
> **THE BRIEF IS LAW**: when a one-off task request conflicts with a standing
> decision here, the brief wins — surface the conflict and ask, never silently
> override.

## Positioning

{scan.description}

Bootstrapped default positioning: a confident, editorial, technically-credible
product that looks designed by a person with taste — not assembled from a SaaS
template.

## Persona

Primary: a discerning operator who has seen a thousand generic dashboards and is
unimpressed by them. Rewards restraint *with* personality.

## Business goals

- Signal craft and seriousness on first contact (3-second test).
- Make the product's actual behavior legible in the hero, not just claimed.

## Brand language

- Editorial, spacious, high-contrast typography.
- Near-black canvas, warm off-white text, **one** amber accent used precisely.
- Mono marginalia as a recurring texture (labels, readouts, annotations).

## Standing design decisions (REQUIRED)

These are commitments, not suggestions. Restraint here produces a blank page —
so this brief commits *toward* richness on purpose:

1. **Ambient background texture is VISIBLE** — opacity ≥ 0.4 (never ≤ 0.25).
   Compose from grid-pattern, dot-pattern, particles; layering two is encouraged.
2. **Every hero shows a product surface in TSX** — a conversation excerpt with
   animated typing, a voice waveform, a command palette, or a status readout.
   A hero without a product surface is incomplete.
3. **Continuous motion — at least two things moving at all times**, idle
   included (drift, breathing pulse, ticker re-roll, blinking caret).
4. **Hover states on at least three elements**, not just the CTA.
5. **Mono marginalia in three+ places, 14–16px** (never 11px).
6. **Massive editorial wordmark**, 96–140px, hand-tuned tracking/leading.
7. **One accent color, used with precision** — no fills, no decorative use.

### Forbidden moves

- ❌ Generic SaaS dark mode (flat gray cards, centered hero, one CTA, nothing moving).
- ❌ The cyberpunk default palette: **violet + cyan**. We are near-black + amber.
- ❌ Near-invisible texture (≤ 0.25 opacity) or motionless heroes.
- ❌ Forbidden fonts (Space Grotesk, Plus Jakarta Sans, Poppins, Montserrat, …).
- ❌ Two competing accent colors, or the accent used as a decorative fill.
- ❌ Stock hero photography standing in for a real product surface.

## Ongoing themes

- Make the invisible visible: surface latency, status, and process as design.

## Bootstrap notes

- Generated by Prism's bootstrap from a repo scan.
- package.json present: {scan.has_package_json}; deps sampled: {", ".join(scan.dependencies[:8]) or "none"}.
- Existing CSS noticed: {", ".join(scan.css_files) or "none"}.
- Treat all of the above as a starting point to be sharpened, not gospel.
"""


def render_feature_md(feature_slug: str, title: str | None = None) -> str:
    title = title or feature_slug.replace("-", " ").title()
    return f"""# Feature — {title}

> PUBLIC, RAPIDLY EVOLVING. The per-feature spec. Mockups for this feature are
> composed into `.prism/preview/app/{feature_slug}/<screen>/page.tsx`.

## Goal

_What is this screen for? Who is looking at it and what do they need to do?_

## Screens

- `hero` — _the primary screen for this feature._

## Visual direction

_Specifics, not adjectives. Name textures, opacities, the product surface, the
motion, the marginalia. The brief's REQUIRED elements apply._

## Content / copy

_Real-ish copy. Placeholder lorem reads as unfinished and anchors generation badly._

## Notes

- Drop reference screenshots in `.prism/references/{feature_slug}/`.
"""


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


@dataclass
class BootstrapResult:
    created_design: bool
    created_brief: bool
    design_path: Path
    brief_path: Path
    scan: RepoScan


def bootstrap_project(slug: str, *, force: bool = False) -> BootstrapResult:
    """Create concrete design.md + brief.md for a project if they don't exist."""
    root = docs.resolve_project_root(slug)
    scan = scan_repo(root)

    design_p = docs.design_doc_path(slug)
    brief_p = docs.brief_path(slug)

    created_design = False
    if force or not design_p.exists():
        docs.write_design_doc(slug, render_design_md(scan, DEFAULT_TOKENS))
        created_design = True

    created_brief = False
    if force or not brief_p.exists():
        docs.write_brief(slug, render_brief_md(scan))
        created_brief = True

    return BootstrapResult(
        created_design=created_design,
        created_brief=created_brief,
        design_path=design_p,
        brief_path=brief_p,
        scan=scan,
    )
