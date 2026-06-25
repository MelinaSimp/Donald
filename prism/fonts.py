"""Curated Google Fonts catalog for the head-of-design agent.

Three roles — display, body, mono — ordered most-distinctive first so the
agent reaches for character before it reaches for the safe default.

``FORBIDDEN_FAMILIES`` blocks fonts that read as "generic AI SaaS". Validation
(``design_tokens.validate``) rejects any token that names a forbidden family,
even though they are perfectly real Google Fonts — the point is taste, not
existence.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FontEntry:
    name: str           # exact Google Fonts family name (next/font/google expects this)
    role: str           # "display" | "body" | "mono"
    note: str           # why you'd reach for it


# Ordered: distinctive choices first within each role.
FONT_CATALOG: dict[str, list[FontEntry]] = {
    "display": [
        FontEntry("Fraunces", "display", "High-contrast 'old style' serif with optical sizing; editorial, warm, opinionated."),
        FontEntry("Instrument Serif", "display", "Tall, elegant single-weight serif; great for oversized editorial wordmarks."),
        FontEntry("Bricolage Grotesque", "display", "Quirky humanist grotesque; condensed energy without feeling techy."),
        FontEntry("Unbounded", "display", "Geometric, very wide, high-impact; brutalist poster headlines."),
        FontEntry("Syne", "display", "Extravagant widths and a wild extra-bold; art-gallery / fashion energy."),
        FontEntry("Playfair Display", "display", "Classic high-contrast didone serif; luxury, fashion, editorial."),
        FontEntry("DM Serif Display", "display", "Tight, high-contrast display serif; confident magazine headlines."),
        FontEntry("Libre Caslon Display", "display", "Refined Caslon display cut; literary, trustworthy, timeless."),
    ],
    "body": [
        FontEntry("Inter Tight", "body", "Tighter Inter; neutral workhorse that still feels deliberate at body sizes."),
        FontEntry("Newsreader", "body", "Reading-optimized serif with optical sizes; long-form, humane."),
        FontEntry("Source Serif 4", "body", "Balanced text serif; pairs cleanly under most display serifs."),
        FontEntry("IBM Plex Sans", "body", "Engineered humanist sans; technical credibility without coldness."),
        FontEntry("Hanken Grotesk", "body", "Friendly geometric grotesque; modern product UI body."),
        FontEntry("Spline Sans", "body", "Compact neo-grotesque; dense dashboards and data UIs."),
        FontEntry("Schibsted Grotesk", "body", "Editorial grotesque with personality; news and product crossover."),
        FontEntry("Figtree", "body", "Clean, slightly rounded sans; approachable consumer product."),
    ],
    "mono": [
        FontEntry("JetBrains Mono", "mono", "Developer-grade mono with ligatures; code annotations, terminals."),
        FontEntry("IBM Plex Mono", "mono", "Warm mono with real character; mono marginalia and labels."),
        FontEntry("Space Mono", "mono", "Retro-futurist mono; status readouts, captions, brutalist accents."),
        FontEntry("Martian Mono", "mono", "Variable-width grotesque mono; striking UPPERCASE micro-labels."),
        FontEntry("DM Mono", "mono", "Low-key geometric mono; understated technical text."),
        FontEntry("Fira Code", "mono", "Ligature-rich coding mono; inline code surfaces."),
    ],
}

# Fonts that signal "generic AI SaaS template". Real fonts, deliberately blocked.
FORBIDDEN_FAMILIES: frozenset[str] = frozenset({
    "Space Grotesk",
    "Plus Jakarta Sans",
    "Poppins",
    "Montserrat",
    "Raleway",
    "Nunito",
    "Quicksand",
    "Comfortaa",
    "Manrope",
})

ROLES = ("display", "body", "mono")

_ALLOWED_BY_ROLE: dict[str, set[str]] = {
    role: {e.name for e in entries} for role, entries in FONT_CATALOG.items()
}
ALL_ALLOWED: frozenset[str] = frozenset(
    name for names in _ALLOWED_BY_ROLE.values() for name in names
)


def is_forbidden(name: str) -> bool:
    return name.strip() in FORBIDDEN_FAMILIES


def is_allowed(name: str, role: str | None = None) -> bool:
    """True if ``name`` is in the catalog (optionally for a given role) and not forbidden."""
    name = name.strip()
    if is_forbidden(name):
        return False
    if role is not None:
        return name in _ALLOWED_BY_ROLE.get(role, set())
    return name in ALL_ALLOWED


def allowed_for_role(role: str) -> list[str]:
    return [e.name for e in FONT_CATALOG.get(role, [])]


def render_for_prompt() -> str:
    """Compact catalog for embedding in a system/CC prompt."""
    lines: list[str] = ["GOOGLE FONTS CATALOG (use exact names; distinctive first):"]
    for role in ROLES:
        names = ", ".join(e.name for e in FONT_CATALOG[role])
        lines.append(f"  {role}: {names}")
    lines.append(
        "FORBIDDEN (never use — they read as generic AI SaaS): "
        + ", ".join(sorted(FORBIDDEN_FAMILIES))
    )
    return "\n".join(lines)
