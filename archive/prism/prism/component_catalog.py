"""The curated component palette the composer (Claude Code) builds from.

Two consumers:
  * ``render_for_prompt()``      -> compact block embedded in the CC -p prompt
  * ``render_full_catalog_markdown()`` -> verbose reference written to
    ``.prism/preview/prism/component_catalog.md`` for CC to Read on demand.

Only libraries with a WORKING CLI are listed as installable (shadcn, MagicUI,
Framer Motion). Aceternity/Reactbits are copy-paste only — listed separately and
explicitly marked *not* auto-installable so CC never runs `npx` against them and
fails. Ship a local snapshot first if you want them in play.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntry:
    name: str
    use_for: str
    install: str          # exact command, or "" for copy-paste-only
    docs: str = ""


SHADCN_INSTALL = "npx shadcn@latest add {name}"
MAGICUI_INSTALL = "npx magicui-cli add {name}"


SHADCN_COMPONENTS: list[CatalogEntry] = [
    CatalogEntry("button", "Primary/secondary/ghost actions, CTAs.", SHADCN_INSTALL.format(name="button")),
    CatalogEntry("card", "Surfaces, panels, product cards.", SHADCN_INSTALL.format(name="card")),
    CatalogEntry("dialog", "Modals, focused tasks.", SHADCN_INSTALL.format(name="dialog")),
    CatalogEntry("sheet", "Side panels, drawers, mobile nav.", SHADCN_INSTALL.format(name="sheet")),
    CatalogEntry("tabs", "Segmented views.", SHADCN_INSTALL.format(name="tabs")),
    CatalogEntry("input", "Text fields.", SHADCN_INSTALL.format(name="input")),
    CatalogEntry("form", "Validated forms (react-hook-form + zod).", SHADCN_INSTALL.format(name="form")),
    CatalogEntry("badge", "Status pills, tags, labels.", SHADCN_INSTALL.format(name="badge")),
    CatalogEntry("avatar", "User/identity glyphs.", SHADCN_INSTALL.format(name="avatar")),
    CatalogEntry("tooltip", "Hover-reveal annotations (use for marginalia).", SHADCN_INSTALL.format(name="tooltip")),
    CatalogEntry("dropdown-menu", "Contextual menus.", SHADCN_INSTALL.format(name="dropdown-menu")),
    CatalogEntry("separator", "Hairline dividers.", SHADCN_INSTALL.format(name="separator")),
    CatalogEntry("scroll-area", "Custom scroll containers (chat logs, lists).", SHADCN_INSTALL.format(name="scroll-area")),
    CatalogEntry("accordion", "Disclosure, FAQs.", SHADCN_INSTALL.format(name="accordion")),
    CatalogEntry("command", "Command palette / cmd-k surfaces.", SHADCN_INSTALL.format(name="command")),
    CatalogEntry("table", "Data tables, readouts.", SHADCN_INSTALL.format(name="table")),
    CatalogEntry("skeleton", "Loading placeholders.", SHADCN_INSTALL.format(name="skeleton")),
    CatalogEntry("sonner", "Toasts/notifications.", SHADCN_INSTALL.format(name="sonner")),
    CatalogEntry("switch", "Toggles.", SHADCN_INSTALL.format(name="switch")),
    CatalogEntry("progress", "Progress / load bars.", SHADCN_INSTALL.format(name="progress")),
]

MAGICUI_COMPONENTS: list[CatalogEntry] = [
    CatalogEntry("grid-pattern", "Ambient grid texture (use at opacity >= 0.4).", MAGICUI_INSTALL.format(name="grid-pattern")),
    CatalogEntry("dot-pattern", "Ambient dot texture; layer under grid.", MAGICUI_INSTALL.format(name="dot-pattern")),
    CatalogEntry("animated-grid-pattern", "Living grid, cells fade in/out (continuous motion).", MAGICUI_INSTALL.format(name="animated-grid-pattern")),
    CatalogEntry("particles", "Drifting particle field (continuous motion).", MAGICUI_INSTALL.format(name="particles")),
    CatalogEntry("flickering-grid", "Flickering cell grid; atmospheric backdrop.", MAGICUI_INSTALL.format(name="flickering-grid")),
    CatalogEntry("border-beam", "Beam that traces an element's border (great on CTA hover).", MAGICUI_INSTALL.format(name="border-beam")),
    CatalogEntry("blur-fade", "Entrance blur-fade for wordmarks/sections.", MAGICUI_INSTALL.format(name="blur-fade")),
    CatalogEntry("text-animate", "Per-character/word text reveal.", MAGICUI_INSTALL.format(name="text-animate")),
    CatalogEntry("typing-animation", "Typewriter effect (animated typing on a line).", MAGICUI_INSTALL.format(name="typing-animation")),
    CatalogEntry("number-ticker", "Animated number roll (continuous metric motion).", MAGICUI_INSTALL.format(name="number-ticker")),
    CatalogEntry("animated-list", "Items animate in sequentially (activity feeds).", MAGICUI_INSTALL.format(name="animated-list")),
    CatalogEntry("marquee", "Infinite horizontal scroller (logos, quotes).", MAGICUI_INSTALL.format(name="marquee")),
    CatalogEntry("bento-grid", "Editorial bento layout.", MAGICUI_INSTALL.format(name="bento-grid")),
    CatalogEntry("animated-beam", "Beam connecting two nodes (system diagrams).", MAGICUI_INSTALL.format(name="animated-beam")),
    CatalogEntry("orbiting-circles", "Orbiting glyphs around a center.", MAGICUI_INSTALL.format(name="orbiting-circles")),
    CatalogEntry("shimmer-button", "Button with a traveling shimmer.", MAGICUI_INSTALL.format(name="shimmer-button")),
    CatalogEntry("ripple", "Concentric ripple backdrop (status pulse).", MAGICUI_INSTALL.format(name="ripple")),
    CatalogEntry("meteors", "Falling meteor streaks.", MAGICUI_INSTALL.format(name="meteors")),
    CatalogEntry("aurora-text", "Aurora-gradient animated heading text.", MAGICUI_INSTALL.format(name="aurora-text")),
    CatalogEntry("word-rotate", "Rotating word swap in a headline.", MAGICUI_INSTALL.format(name="word-rotate")),
]

# npm-installable motion primitive.
FRAMER_MOTION = CatalogEntry(
    "framer-motion",
    "Custom motion when libraries don't cover it (scanline drift, breathing "
    "pulse, oscillating waveform, blinking caret).",
    "npm install framer-motion",
)

# Copy-paste only — NO CLI. Not installable until a local snapshot is bundled.
SNAPSHOT_ONLY: list[CatalogEntry] = [
    CatalogEntry("aceternity:spotlight", "Spotlight / background-beams / tracing-beam / 3D card.", ""),
    CatalogEntry("reactbits:text-effects", "Text effects, scroll animations.", ""),
]


def _fmt(entries: list[CatalogEntry]) -> str:
    return "\n".join(f"  - {e.name}: {e.use_for}" for e in entries)


def render_for_prompt() -> str:
    """Compact palette for the CC -p prompt / system prompt."""
    lines = [
        "COMPONENT PALETTE (install only via the commands below; nothing else):",
        "",
        "shadcn/ui — every primitive. Install: `npx shadcn@latest add <name>`",
        _fmt(SHADCN_COMPONENTS),
        "",
        "MagicUI — motion + texture + heroes. Install: `npx magicui-cli add <name>`",
        _fmt(MAGICUI_COMPONENTS),
        "",
        f"Framer Motion — {FRAMER_MOTION.use_for} Install: `{FRAMER_MOTION.install}`",
        "",
        "NOT AVAILABLE (copy-paste only; no snapshot bundled — do NOT npx these):",
        _fmt(SNAPSHOT_ONLY),
    ]
    return "\n".join(lines)


def render_full_catalog_markdown() -> str:
    """Verbose reference dropped into .prism/preview/prism/component_catalog.md."""
    def table(entries: list[CatalogEntry]) -> str:
        rows = ["| Component | Use for | Install |", "|---|---|---|"]
        for e in entries:
            install = f"`{e.install}`" if e.install else "_copy-paste only_"
            rows.append(f"| `{e.name}` | {e.use_for} | {install} |")
        return "\n".join(rows)

    return f"""# Component Catalog

This is the full palette available to you when composing screens. **Install only
via the exact commands listed.** Do not invent components or install libraries
not listed here.

## shadcn/ui — primitives

Install: `npx shadcn@latest add <name>`

{table(SHADCN_COMPONENTS)}

## MagicUI — motion, texture, heroes

Install: `npx magicui-cli add <name>`

{table(MAGICUI_COMPONENTS)}

## Framer Motion

{table([FRAMER_MOTION])}

Use for bespoke continuous motion: scanline drift, breathing pulses, oscillating
voice waveforms, blinking carets, number tickers.

## Not available (copy-paste only)

These libraries have **no CLI** and **no local snapshot is bundled** in this
project. Do not attempt to `npx` them — the install will fail. They are listed
only so you know what *could* be added later.

{table(SNAPSHOT_ONLY)}

## Rules

- **Installing a component is not using it.** Every component you install must
  appear in the rendered TSX. Audit your own page before declaring done.
- Prefer MagicUI for ambient texture and continuous motion; shadcn for structure
  and primitives; Framer Motion for anything bespoke.
"""


# Convenience name lists (used by validation / prompt hints elsewhere).
SHADCN_NAMES = [e.name for e in SHADCN_COMPONENTS]
MAGICUI_NAMES = [e.name for e in MAGICUI_COMPONENTS]
