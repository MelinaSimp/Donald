"""Audit a composed page's TSX against the REQUIRED visual elements (Tier 6).

The cardinal anti-pattern: ``npx <something>`` succeeding is NOT evidence the
component appears in the rendered page. So we audit the *written TSX*, not the
install log. This is a heuristic gate — it can't judge taste, but it reliably
catches the "competent but empty" failure mode (no texture, no motion, no
product surface, marginalia missing or too small).

Used two ways:
  * by ``tools.execute_generate_mockup`` to attach warnings to the result, and
  * as the deterministic backbone of the Tier 6 ship test.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# MagicUI / ambient background components that count as "visible texture".
_BG_COMPONENTS = (
    "GridPattern", "AnimatedGridPattern", "DotPattern", "Particles",
    "FlickeringGrid", "Meteors", "Ripple",
)

# Signals that a TSX-composed product surface is present.
_PRODUCT_SURFACE_SIGNALS = (
    "waveform", "typing", "TypingAnimation", "command palette", "Command",
    "status", "readout", "transcript", "conversation", "caret", "terminal",
)

# Continuous-motion signals (Tailwind animate-*, framer-motion, MagicUI motion).
_MOTION_SIGNALS = (
    "animate-", "motion.", "BorderBeam", "NumberTicker", "TypingAnimation",
    "Marquee", "AnimatedList", "ShimmerButton", "Ripple", "AuroraText",
)

# A border-beam-on-hover (or equivalent emphasis-on-hover) signal.
_BEAM_HOVER = ("BorderBeam", "ShimmerButton", "group-hover", "hover:border")


@dataclass
class AuditReport:
    has_ambient_background: bool
    has_product_surface: bool
    has_continuous_motion: bool
    mono_uppercase_count: int
    hover_count: int
    has_beam_or_hover_emphasis: bool
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures


def _count_mono_uppercase(text: str) -> int:
    """Count elements that pair font-mono with uppercase (the marginalia idiom)."""
    count = 0
    # className strings that contain both font-mono and uppercase.
    for m in re.finditer(r"className=(?:\"|'|\{`)([^\"'`]*)", text):
        cls = m.group(1)
        if "font-mono" in cls and "uppercase" in cls:
            count += 1
    return count


def audit_page_tsx(text: str) -> AuditReport:
    text = text or ""
    has_bg = any(c in text for c in _BG_COMPONENTS)
    has_surface = any(s.lower() in text.lower() for s in _PRODUCT_SURFACE_SIGNALS)
    has_motion = any(s in text for s in _MOTION_SIGNALS)
    mono_upper = _count_mono_uppercase(text)
    hover_count = len(re.findall(r"hover:", text)) + len(re.findall(r"group-hover:", text))
    has_beam = any(s in text for s in _BEAM_HOVER)

    failures: list[str] = []
    if not has_bg:
        failures.append(
            "no visible ambient background component (expected one of "
            + ", ".join(_BG_COMPONENTS) + ")."
        )
    if not has_surface:
        failures.append("no inline product surface (waveform/typing/status/command/transcript).")
    if not has_motion:
        failures.append("no continuous motion (animate-*, motion., BorderBeam, NumberTicker, …).")
    if mono_upper < 3:
        failures.append(f"only {mono_upper} font-mono+uppercase marginalia; need >= 3.")
    if hover_count < 3:
        failures.append(f"only {hover_count} hover states; need >= 3 (not just the CTA).")
    if not has_beam:
        failures.append("no border-beam / shimmer / hover-emphasis element.")

    return AuditReport(
        has_ambient_background=has_bg,
        has_product_surface=has_surface,
        has_continuous_motion=has_motion,
        mono_uppercase_count=mono_upper,
        hover_count=hover_count,
        has_beam_or_hover_emphasis=has_beam,
        failures=failures,
    )
