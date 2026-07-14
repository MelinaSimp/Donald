"""Source reliability tiering for grounded answers.

Ported from Drift's ``lib/dante/source-tiers.ts``. Every data source a brain
draws on is tagged with a *tier* so the model uses confidence language that
matches how trustworthy the source actually is:

* **Tier 1** — government primary data → "Census data shows…" (definitive)
* **Tier 2** — commercial data provider → "Per CoStar data…" (sourced)
* **Tier 3** — web search / news → "Reports suggest…" (hedged)

The tiering is pure data + a prompt-formatting helper; there are no runtime
dependencies, which is why it ports across from the TypeScript product
unchanged. ``format_tier_guidance()`` produces a block suitable for injecting
into a brain's system prompt.
"""

from __future__ import annotations

from dataclasses import dataclass

# Tier is one of 1, 2, 3. Kept as a plain int (with this alias for readers)
# rather than an Enum so the tags below stay literal and JSON-friendly.
SourceTier = int


@dataclass(frozen=True)
class SourceTag:
    """A single data source tagged with its reliability tier."""

    tier: SourceTier
    source: str


@dataclass(frozen=True)
class _TierMeta:
    tier: SourceTier
    label: str
    examples: str
    guidance: str


_TIERS: tuple[_TierMeta, ...] = (
    _TierMeta(
        tier=1,
        label="Government primary data",
        examples=(
            "Census ACS, BLS employment, FEMA flood maps, EPA TRI/Superfund, "
            "county assessor records"
        ),
        guidance=(
            "Cite as authoritative. Use definitive language: 'Census data shows', "
            "'the area has', 'BLS reports'. No hedging needed unless the vintage is "
            "dated (e.g. 5-year ACS estimates have a lag)."
        ),
    ),
    _TierMeta(
        tier=2,
        label="Commercial data provider",
        examples="CoStar, Yardi, Reonomy, Regrid, Google Maps, Placer.ai",
        guidance=(
            "Cite the provider by name: 'per CoStar data', 'Yardi records indicate'. "
            "Confident but sourced. Note that commercial data is independently "
            "compiled but may lag real-time conditions."
        ),
    ),
    _TierMeta(
        tier=3,
        label="Web search / news",
        examples=(
            "News articles, broker marketing sites, public records aggregators, forums"
        ),
        guidance=(
            "Cite the specific source by name or URL. Use hedged language: 'reports "
            "suggest', 'according to [source]'. Flag if only one source corroborates "
            "a claim. If a Tier 3 source contradicts Tier 1, note the discrepancy and "
            "defer to the authoritative source. Watch for self-referential sources (a "
            "publication citing itself as authoritative is not independent "
            "corroboration)."
        ),
    ),
)


def format_tier_guidance() -> str:
    """Return a formatted block for injection into a brain's system prompt.

    Tells the model how to handle each reliability tier when it grounds claims.
    """
    return "\n\n".join(
        f"TIER {t.tier} -- {t.label}\n"
        f"Examples: {t.examples}\n"
        f"Guidance: {t.guidance}"
        for t in _TIERS
    )


# Pre-built tags for known data sources.
TAGS: dict[str, SourceTag] = {
    "census": SourceTag(1, "U.S. Census Bureau ACS 5-Year Estimates"),
    "bls": SourceTag(1, "Bureau of Labor Statistics QCEW"),
    "fema": SourceTag(1, "FEMA National Flood Hazard Layer"),
    "epa_tri": SourceTag(1, "EPA Toxics Release Inventory"),
    "epa_superfund": SourceTag(1, "EPA Superfund / CERCLIS"),
    "google_places": SourceTag(2, "Google Maps Places API"),
    "google_distance": SourceTag(2, "Google Maps Distance Matrix API"),
    "nominatim": SourceTag(2, "OpenStreetMap / Nominatim"),
    "web_search": SourceTag(3, "Web search (Tavily)"),
}
