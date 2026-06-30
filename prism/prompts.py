"""Tier 3/6/7 — prompt construction.

Two audiences:
  * the planning agent's system prompt (``system_prompt``) — carries the two
    non-negotiable sections (THE BRIEF IS LAW; visual elements are REQUIRED),
    the component palette, and the font catalog.
  * Claude Code's ``-p`` prompt (``build_cc_prompt``) — heavily opinionated, ~4-6KB:
    which files to read first, scaffold steps, the palette + install commands,
    the required visual elements, the quality bar, the forbidden moves, the
    reference-image block, the image-URL rules, and the exact output path + build.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import component_catalog, fonts

# ---------------------------------------------------------------------------
# The two non-negotiable system-prompt sections (Tier 6)
# ---------------------------------------------------------------------------

BRIEF_IS_LAW = """\
## THE BRIEF IS LAW

`.prism/brief.md` encodes the user's standing design decisions, including
explicit FORBIDDEN MOVES. These are commitments, not suggestions.

- When a one-off task request (or the user's voice cue) conflicts with the
  brief, **the brief wins**. A task saying "make it sci-fi" does NOT override a
  brief that forbids sci-fi.
- Never silently override the brief based on task wording. Surface the conflict
  in `open_questions` and ASK before proceeding.
- The brief's palette, forbidden colors, and forbidden fonts are hard
  constraints carried all the way down into image prompts and TSX."""

VISUAL_ELEMENTS_REQUIRED = """\
## VISUAL ELEMENTS ARE REQUIRED, PRESENT, CONTINUOUS

Every hero MUST include ALL of the following. Absence = incomplete, not stylistic
choice. Rule of thumb: if a viewer staring for 3 seconds can't tell anything is
moving, the page FAILED.

1. **Ambient background texture — VISIBLE** (opacity >= 0.4, never <= 0.25).
   Pick from grid-pattern, dot-pattern, particles. Layering two is encouraged.
2. **An inline product surface in TSX** showing what the product *does*:
   a conversation excerpt with animated typing, a voice waveform, a command
   palette, a status readout, a code-annotation overlay. A hero without a
   product surface is incomplete.
3. **Continuous motion — at least two things running at all times** (not just on
   load): scanline drift, breathing pulse, number tickers, oscillating waveform,
   blinking caret.
4. **Hover states on at least three elements** — not only the CTA.
5. **Three+ mono marginalia annotations**, sized 14-16px (NOT 11px).

`visual_direction` must name specifics, not adjectives.
- BAD:  "premium cyberpunk hero"
- GOOD: "grid-pattern at 0.5 opacity layered with drifting amber particles;
  conversation excerpt in mono with typing-animation on the latest line;
  breathing amber status pulse labeled `LISTENING · 287ms`; blur-fade on the
  wordmark; border-beam on CTA hover; hover-reveal tooltips on three mono
  marginalia annotations." """

QUALITY_BAR = """\
## QUALITY BAR

A passing dispatch produces, on ONE page:
- Layered ambient texture (e.g. grid + drifting particles), both visible at first
  glance.
- A massive editorial wordmark at display scale (96-140px) with hand-tuned
  tracking and leading.
- Two or three product surfaces composed in TSX (status readout + conversation
  excerpt + voice waveform).
- Any AI-generated images referenced via plain `<img>` tags using the FULL URLs
  provided.
- Continuous motion: multiple things moving even when idle.
- Mono marginalia in three+ places, sized to be seen.
- ONE accent color used with precision — no decorative fills, not the category
  default."""


def system_prompt() -> str:
    """The planning agent's system prompt."""
    return "\n\n".join(
        [
            "You are Prism, the head of design. You take a design task and ship an "
            "actually-good Next.js + Tailwind + shadcn screen — real Google Fonts, "
            "composed components, AI-generated atmospheric imagery, live animation. "
            "You do NOT hand-author vanilla HTML; the substrate caps the ceiling.",
            "Your loop: read design.md + .prism/brief.md + the feature spec; decide "
            "what imagery the screen needs and call `generate_image` once per image "
            "BEFORE composing; then call `generate_mockup`, passing the image URLs "
            "verbatim in `visual_direction`.",
            BRIEF_IS_LAW,
            VISUAL_ELEMENTS_REQUIRED,
            QUALITY_BAR,
            fonts.render_for_prompt(),
            component_catalog.render_for_prompt(),
        ]
    )


# ---------------------------------------------------------------------------
# Claude Code -p prompt (Tier 3/6/7)
# ---------------------------------------------------------------------------


@dataclass
class CCPromptInputs:
    slug: str
    feature_slug: str
    screen_name: str
    description: str
    visual_direction: str
    quality: str
    first_dispatch: bool
    expected_out_path: str          # e.g. out/<feature>/<screen>/index.html
    page_path: str                  # e.g. app/<feature>/<screen>/page.tsx
    url_prefix: str
    components_hint: list[str]
    reference_relpaths: list[str]   # validated, relative to .prism/references/<feature>/
    image_urls: list[str]


def _scaffold_steps(inp: CCPromptInputs) -> str:
    if inp.first_dispatch:
        return (
            "FIRST DISPATCH for this project — run, in order:\n"
            "  1. `npm install` in .prism/preview/\n"
            "  2. `npx shadcn@latest add <names>` for the shadcn primitives you need\n"
            "  3. `npx magicui-cli add <names>` for the MagicUI texture/motion you need\n"
        )
    return (
        "NOT the first dispatch — the scaffold and node_modules already exist. "
        "Do NOT re-run `npm install`. Only `npx shadcn@latest add` / "
        "`npx magicui-cli add` for components not already present.\n"
    )


def _references_block(inp: CCPromptInputs) -> str:
    if not inp.reference_relpaths:
        return ""
    listed = "\n".join(
        f"  - .prism/references/{inp.feature_slug}/{rp}" for rp in inp.reference_relpaths
    )
    return (
        "## REFERENCE IMAGES — READ THESE FIRST WITH THE Read TOOL\n"
        "Claude has vision and will actually SEE these images. Open each one and "
        "anchor your visual decisions against it — references OVERRIDE category "
        "defaults.\n" + listed + "\n"
    )


def _images_block(inp: CCPromptInputs) -> str:
    if not inp.image_urls:
        return ""
    listed = "\n".join(f"  - {u}" for u in inp.image_urls)
    n = len(inp.image_urls)
    return (
        f"## AI-GENERATED IMAGES ({n}) — reference ALL of them\n"
        "Use the FULL URL verbatim in plain `<img>` tags. Do NOT strip the "
        "basePath prefix — plain `<img>` tags don't auto-prefix (only next/image "
        "does, and we don't use it here).\n"
        f"You MUST output exactly {n} `<img>` tag(s); do not silently drop any.\n"
        + listed + "\n"
    )


def build_cc_prompt(inp: CCPromptInputs) -> str:
    hint = ", ".join(inp.components_hint) if inp.components_hint else "(decide from the palette)"
    blocks = [
        f"You are composing ONE high-fidelity screen for project `{inp.slug}`, "
        f"feature `{inp.feature_slug}`, screen `{inp.screen_name}`. Work inside "
        "the Next.js preview app at `.prism/preview/`.",

        "## READ FIRST (use the Read tool)\n"
        "  - design.md  (the design system + the ```yaml tokens block — obey it)\n"
        "  - .prism/brief.md  (standing decisions + FORBIDDEN MOVES)\n"
        f"  - features/{inp.feature_slug}.md  (this feature's spec, if present)\n"
        "  - .prism/preview/prism/component_catalog.md  (what you may install)",

        _references_block(inp),

        "## THE BRIEF IS LAW\n"
        "If anything below conflicts with .prism/brief.md, the brief wins. Do not "
        "silently override it. If you cannot honor both the task and the brief, "
        "stop and say so in your final message rather than guessing.",

        "## SCAFFOLD\n" + _scaffold_steps(inp),

        component_catalog.render_for_prompt(),

        VISUAL_ELEMENTS_REQUIRED,

        f"## THE TASK\n{inp.description}",

        f"## VISUAL DIRECTION (follow precisely; these are not suggestions)\n"
        f"{inp.visual_direction}",

        f"Suggested components to reach for: {hint}.",

        _images_block(inp),

        QUALITY_BAR,

        "## FORBIDDEN MOVES\n"
        "- No vanilla-HTML look; compose real components.\n"
        "- No generic SaaS dark mode (flat gray cards, centered hero, one CTA, "
        "nothing moving).\n"
        "- No category-default palette (e.g. violet+cyan cyberpunk) — obey the "
        "brief's colors.\n"
        "- No forbidden fonts.\n"
        "- Installing a component is NOT using it: every component you install "
        "MUST appear in the rendered TSX.",

        f"## OUTPUT\n"
        f"Write the screen to `{inp.page_path}` (a client component — start the "
        "file with `\"use client\";` if it uses motion/state).\n"
        f"Then run `npm run build` in `.prism/preview/`. The static export must "
        f"produce `{inp.expected_out_path}`. If the build fails, fix it and "
        "rebuild until it succeeds. Do not finish with a broken build.",
    ]
    return "\n\n".join(b for b in blocks if b.strip())
