"""Parse, validate and render the structured design-token block from design.md.

design.md carries a fenced ```yaml tokens block that this module is the sole
authority over. Everything downstream (the Tailwind config, globals.css, the
shadcn components.json, the next/font wiring) is rendered from the parsed
``DesignTokens`` — there is one source of truth, and it is machine-checked.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

from . import fonts

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TokenValidationError(ValueError):
    """Raised when design.md's token block is missing, malformed, or invalid."""


# ---------------------------------------------------------------------------
# Constants / validation primitives
# ---------------------------------------------------------------------------

# #RGB, #RRGGBB, #RRGGBBAA
HEX_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")

# The fenced block we own: ```yaml tokens ... ```
_TOKENS_BLOCK_RE = re.compile(
    r"```yaml\s+tokens\s*\n(?P<body>.*?)\n```",
    re.DOTALL,
)

SHADCN_BASE_COLORS = ("gray", "neutral", "slate", "stone", "zinc")
SHADCN_STYLES = ("default", "new-york")

# Semantic color roles we render into shadcn CSS variables. `background` and
# `foreground` are required; the rest fall back to sensible derivations.
REQUIRED_COLORS = ("background", "foreground", "primary", "accent")
OPTIONAL_COLORS = ("muted", "border", "card", "secondary", "destructive", "ring")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DesignTokens:
    fonts: dict[str, str]            # {"display","body","mono"} -> Google Font name
    colors: dict[str, str]          # role -> hex string
    radius: str                     # e.g. "0.5rem"
    base_color: str                 # shadcn base color enum
    style: str                      # shadcn style enum
    raw: dict = field(default_factory=dict, compare=False)

    @property
    def display_font(self) -> str:
        return self.fonts["display"]

    @property
    def body_font(self) -> str:
        return self.fonts["body"]

    @property
    def mono_font(self) -> str:
        return self.fonts["mono"]


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def extract_tokens_block(markdown_text: str) -> str:
    m = _TOKENS_BLOCK_RE.search(markdown_text)
    if not m:
        raise TokenValidationError(
            "design.md is missing its ```yaml tokens block. The design system is "
            "half-shaped; refusing to compose against it."
        )
    return m.group("body")


def parse_tokens(markdown_text: str) -> DesignTokens:
    """Extract, parse and fully validate the token block from design.md text."""
    body = extract_tokens_block(markdown_text)
    try:
        data = yaml.safe_load(body)
    except yaml.YAMLError as exc:  # pragma: no cover - exercised via malformed input
        raise TokenValidationError(f"tokens block is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise TokenValidationError("tokens block must be a YAML mapping.")

    tokens = _build(data)
    validate(tokens)
    return tokens


def _build(data: dict) -> DesignTokens:
    fonts_in = data.get("fonts") or {}
    colors_in = data.get("colors") or {}
    shadcn_in = data.get("shadcn") or {}
    if not isinstance(fonts_in, dict):
        raise TokenValidationError("`fonts` must be a mapping of role -> family name.")
    if not isinstance(colors_in, dict):
        raise TokenValidationError("`colors` must be a mapping of role -> hex.")
    if not isinstance(shadcn_in, dict):
        raise TokenValidationError("`shadcn` must be a mapping.")

    return DesignTokens(
        fonts={k: str(v).strip() for k, v in fonts_in.items()},
        colors={k: str(v).strip() for k, v in colors_in.items()},
        radius=str(data.get("radius", "0.5rem")).strip(),
        base_color=str(shadcn_in.get("base_color", "neutral")).strip(),
        style=str(shadcn_in.get("style", "new-york")).strip(),
        raw=data,
    )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate(tokens: DesignTokens) -> None:
    """Raise TokenValidationError on the first problem found."""
    # Fonts: all three roles, each a catalog font, none forbidden.
    for role in fonts.ROLES:
        name = tokens.fonts.get(role)
        if not name:
            raise TokenValidationError(f"missing `{role}` font in tokens.")
        if fonts.is_forbidden(name):
            raise TokenValidationError(
                f"font '{name}' ({role}) is forbidden — it signals generic AI SaaS."
            )
        if not fonts.is_allowed(name, role):
            allowed = ", ".join(fonts.allowed_for_role(role))
            raise TokenValidationError(
                f"font '{name}' is not in the curated {role} catalog. Choose one of: {allowed}"
            )

    # Colors: required roles present; every value a valid hex.
    for role in REQUIRED_COLORS:
        if role not in tokens.colors:
            raise TokenValidationError(f"missing required color `{role}`.")
    for role, value in tokens.colors.items():
        if not HEX_RE.match(value):
            raise TokenValidationError(
                f"color `{role}` = '{value}' is not a valid hex (#RGB / #RRGGBB / #RRGGBBAA)."
            )

    # Radius: a CSS length.
    if not re.match(r"^\d*\.?\d+(px|rem|em)$", tokens.radius):
        raise TokenValidationError(f"radius '{tokens.radius}' is not a CSS length (px/rem/em).")

    # shadcn enums.
    if tokens.base_color not in SHADCN_BASE_COLORS:
        raise TokenValidationError(
            f"shadcn.base_color '{tokens.base_color}' invalid; one of {SHADCN_BASE_COLORS}."
        )
    if tokens.style not in SHADCN_STYLES:
        raise TokenValidationError(
            f"shadcn.style '{tokens.style}' invalid; one of {SHADCN_STYLES}."
        )


# ---------------------------------------------------------------------------
# Color conversion (hex -> HSL string for shadcn CSS variables)
# ---------------------------------------------------------------------------


def _expand_hex(hex_str: str) -> tuple[int, int, int]:
    h = hex_str.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    h = h[:6]  # drop alpha for HSL channel math
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def hex_to_hsl(hex_str: str) -> tuple[float, float, float]:
    r, g, b = (c / 255.0 for c in _expand_hex(hex_str))
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2.0
    if mx == mn:
        h = s = 0.0
    else:
        d = mx - mn
        s = d / (2.0 - mx - mn) if l > 0.5 else d / (mx + mn)
        if mx == r:
            h = (g - b) / d + (6.0 if g < b else 0.0)
        elif mx == g:
            h = (b - r) / d + 2.0
        else:
            h = (r - g) / d + 4.0
        h /= 6.0
    return h * 360.0, s * 100.0, l * 100.0


def hsl_var(hex_str: str) -> str:
    """shadcn CSS-variable channel format, e.g. '38 92% 50%'."""
    h, s, l = hex_to_hsl(hex_str)
    return f"{round(h)} {round(s)}% {round(l)}%"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _color(tokens: DesignTokens, role: str, fallback: str) -> str:
    return tokens.colors.get(role, fallback)


def render_globals_css(tokens: DesignTokens) -> str:
    """Tailwind directives + shadcn CSS variables derived from the hex tokens."""
    bg = _color(tokens, "background", "#0a0a0b")
    fg = _color(tokens, "foreground", "#fafafa")
    primary = _color(tokens, "primary", "#f59e0b")
    accent = _color(tokens, "accent", primary)
    muted = _color(tokens, "muted", "#1c1c1f")
    card = _color(tokens, "card", bg)
    border = _color(tokens, "border", muted)
    secondary = _color(tokens, "secondary", muted)
    destructive = _color(tokens, "destructive", "#ef4444")
    ring = _color(tokens, "ring", accent)

    return f""":root {{
  --background: {hsl_var(bg)};
  --foreground: {hsl_var(fg)};
  --card: {hsl_var(card)};
  --card-foreground: {hsl_var(fg)};
  --popover: {hsl_var(card)};
  --popover-foreground: {hsl_var(fg)};
  --primary: {hsl_var(primary)};
  --primary-foreground: {hsl_var(bg)};
  --secondary: {hsl_var(secondary)};
  --secondary-foreground: {hsl_var(fg)};
  --muted: {hsl_var(muted)};
  --muted-foreground: {hsl_var(fg)};
  --accent: {hsl_var(accent)};
  --accent-foreground: {hsl_var(bg)};
  --destructive: {hsl_var(destructive)};
  --destructive-foreground: {hsl_var(fg)};
  --border: {hsl_var(border)};
  --input: {hsl_var(border)};
  --ring: {hsl_var(ring)};
  --radius: {tokens.radius};
}}

@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {{
  * {{
    @apply border-border;
  }}
  body {{
    @apply bg-background text-foreground;
    font-feature-settings: "rlig" 1, "calt" 1;
  }}
}}
"""


def render_tailwind_config(tokens: DesignTokens) -> str:
    """tailwind.config.ts wired to the CSS variables and the next/font variables."""
    return """import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./pages/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./app/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    container: { center: true, padding: "2rem", screens: { "2xl": "1400px" } },
    extend: {
      fontFamily: {
        display: ["var(--font-display)"],
        sans: ["var(--font-body)"],
        mono: ["var(--font-mono)"],
      },
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "accordion-down": {
          from: { height: "0" },
          to: { height: "var(--radix-accordion-content-height)" },
        },
        "accordion-up": {
          from: { height: "var(--radix-accordion-content-height)" },
          to: { height: "0" },
        },
      },
      animation: {
        "accordion-down": "accordion-down 0.2s ease-out",
        "accordion-up": "accordion-up 0.2s ease-out",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
"""


def render_components_json(tokens: DesignTokens) -> str:
    """shadcn components.json driven by the token base-color and style."""
    return f"""{{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "{tokens.style}",
  "rsc": true,
  "tsx": true,
  "tailwind": {{
    "config": "tailwind.config.ts",
    "css": "app/globals.css",
    "baseColor": "{tokens.base_color}",
    "cssVariables": true,
    "prefix": ""
  }},
  "aliases": {{
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/components/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  }},
  "iconLibrary": "lucide"
}}
"""
