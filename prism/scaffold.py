"""Tier 2 — the per-project preview app scaffold (the architectural keystone).

Every project gets a Next.js 15 + Tailwind + shadcn app at
``<project>/.prism/preview/``. This is the substrate mockups compose onto; a real
component framework is what lifts output above the vanilla-HTML quality ceiling.

``prepare_scaffold`` is idempotent: if ``package.json`` already exists it reports
``skipped=True`` and leaves the app untouched (so npm install / installed
components survive across dispatches).

Three crucial next.config settings, each guarding a documented stumbling block:
  * output: 'export'       -> static export, no Node runtime at view time
  * trailingSlash: true    -> each route emits out/<path>/index.html (predictable)
  * basePath + assetPrefix -> Next-emitted URLs resolve under the serving prefix
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import component_catalog, docs, fonts
from . import design_tokens as dt


def default_url_prefix(slug: str) -> str:
    return f"/api/{slug}/preview"


# ---------------------------------------------------------------------------
# File renderers
# ---------------------------------------------------------------------------


def render_package_json(slug: str) -> str:
    return f"""{{
  "name": "{slug}-prism-preview",
  "private": true,
  "version": "0.1.0",
  "scripts": {{
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  }},
  "dependencies": {{
    "next": "^15.1.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "class-variance-authority": "^0.7.1",
    "clsx": "^2.1.1",
    "tailwind-merge": "^2.6.0",
    "tailwindcss-animate": "^1.0.7",
    "lucide-react": "^0.469.0"
  }},
  "devDependencies": {{
    "typescript": "^5.7.0",
    "@types/node": "^22.10.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "tailwindcss": "^3.4.17",
    "postcss": "^8.4.49",
    "autoprefixer": "^10.4.20"
  }}
}}
"""


def render_next_config(url_prefix: str) -> str:
    return f"""/** @type {{import('next').NextConfig}} */
const nextConfig = {{
  // Static export: no Node runtime needed at view time.
  output: 'export',
  // Each route -> out/<path>/index.html (predictable for the serving endpoint).
  trailingSlash: true,
  // Next-emitted asset URLs resolve correctly when served under the prefix.
  basePath: '{url_prefix}',
  assetPrefix: '{url_prefix}',
  // Plain <img> + static export: no optimizer at view time.
  images: {{ unoptimized: true }},
  eslint: {{ ignoreDuringBuilds: true }},
  typescript: {{ ignoreBuildErrors: true }},
}};

export default nextConfig;
"""


def render_tsconfig() -> str:
    return """{
  "compilerOptions": {
    "target": "ES2020",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules", "out"]
}
"""


def render_postcss_config() -> str:
    return """const config = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};

export default config;
"""


def render_lib_utils() -> str:
    return """import { type ClassValue, clsx } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
"""


def render_lib_fonts(tokens: dt.DesignTokens) -> str:
    """lib/fonts.ts — next/font/google for the three families with CSS variables."""
    roles = [
        ("display", tokens.display_font, "--font-display"),
        ("body", tokens.body_font, "--font-body"),
        ("mono", tokens.mono_font, "--font-mono"),
    ]
    imports = []
    decls = []
    for role, family, var in roles:
        imp = fonts.google_import_name(family)
        imports.append(imp)
        weights = fonts.weights_for(family)
        if weights:
            weight_js = "[" + ", ".join(f'"{w}"' for w in weights) + "]"
            decls.append(
                f'export const {role}Font = {imp}({{\n'
                f'  subsets: ["latin"],\n'
                f'  weight: {weight_js},\n'
                f'  variable: "{var}",\n'
                f'  display: "swap",\n}});'
            )
        else:
            decls.append(
                f'export const {role}Font = {imp}({{\n'
                f'  subsets: ["latin"],\n'
                f'  variable: "{var}",\n'
                f'  display: "swap",\n}});'
            )
    import_line = "import { " + ", ".join(dict.fromkeys(imports)) + ' } from "next/font/google";'
    body = "\n\n".join(decls)
    return f"""{import_line}

{body}

export const fontVariables = `${{displayFont.variable}} ${{bodyFont.variable}} ${{monoFont.variable}}`;
"""


def render_layout(slug: str, tokens: dt.DesignTokens) -> str:
    return f"""import type {{ Metadata }} from "next";
import {{ fontVariables }} from "@/lib/fonts";
import "./globals.css";

export const metadata: Metadata = {{
  title: "{slug} — Prism preview",
  description: "High-fidelity mockups composed by the Prism head-of-design agent.",
}};

export default function RootLayout({{
  children,
}}: {{
  children: React.ReactNode;
}}) {{
  return (
    <html lang="en" className={{`dark ${{fontVariables}}`}}>
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        {{children}}
      </body>
    </html>
  );
}}
"""


def render_index_page(slug: str, url_prefix: str) -> str:
    """A build-time directory read listing the composed mockups."""
    return f"""import {{ promises as fs }} from "fs";
import path from "path";

// Read at build time (static export) so the index lists whatever screens exist.
async function listMockups(): Promise<{{ feature: string; screen: string }}[]> {{
  const appDir = path.join(process.cwd(), "app");
  const out: {{ feature: string; screen: string }}[] = [];
  let features: string[] = [];
  try {{
    features = await fs.readdir(appDir);
  }} catch {{
    return out;
  }}
  for (const feature of features) {{
    const featureDir = path.join(appDir, feature);
    let stat;
    try {{ stat = await fs.stat(featureDir); }} catch {{ continue; }}
    if (!stat.isDirectory()) continue;
    let screens: string[] = [];
    try {{ screens = await fs.readdir(featureDir); }} catch {{ continue; }}
    for (const screen of screens) {{
      try {{
        await fs.access(path.join(featureDir, screen, "page.tsx"));
        out.push({{ feature, screen }});
      }} catch {{ /* not a screen */ }}
    }}
  }}
  return out;
}}

export default async function Home() {{
  const mockups = await listMockups();
  return (
    <main className="mx-auto max-w-3xl px-6 py-24">
      <p className="font-mono text-sm uppercase tracking-widest text-muted-foreground">
        {slug} · prism preview
      </p>
      <h1 className="mt-4 font-display text-5xl tracking-tight">Composed screens</h1>
      <ul className="mt-12 divide-y divide-border border-y border-border">
        {{mockups.length === 0 && (
          <li className="py-6 font-mono text-sm text-muted-foreground">
            No screens yet. Dispatch a design task to compose one.
          </li>
        )}}
        {{mockups.map(({{ feature, screen }}) => (
          <li key={{`${{feature}}/${{screen}}`}} className="py-6">
            <a
              href={{`{url_prefix}/${{feature}}/${{screen}}/`}}
              className="group flex items-baseline justify-between"
            >
              <span className="font-display text-2xl">{{feature}} / {{screen}}</span>
              <span className="font-mono text-xs uppercase tracking-widest text-muted-foreground group-hover:text-foreground">
                view →
              </span>
            </a>
          </li>
        ))}}
      </ul>
    </main>
  );
}}
"""


def render_gitignore() -> str:
    return "node_modules/\n.next/\nout/\n*.tsbuildinfo\nnext-env.d.ts\n"


# ---------------------------------------------------------------------------
# Scaffolder
# ---------------------------------------------------------------------------


@dataclass
class ScaffoldResult:
    skipped: bool
    preview_dir: Path
    url_prefix: str
    files_written: list[str] = field(default_factory=list)


SCAFFOLD_SENTINEL = "package.json"


def prepare_scaffold(
    project_root: Path,
    tokens: dt.DesignTokens,
    slug: str,
    url_prefix: str | None = None,
) -> ScaffoldResult:
    """Write the ~13-file Next.js preview scaffold. Idempotent (skips if present)."""
    project_root = Path(project_root)
    url_prefix = url_prefix or default_url_prefix(slug)
    preview = project_root / docs.PRISM_DIRNAME / "preview"

    if (preview / SCAFFOLD_SENTINEL).exists():
        return ScaffoldResult(skipped=True, preview_dir=preview, url_prefix=url_prefix)

    files: dict[str, str] = {
        "package.json": render_package_json(slug),
        "next.config.mjs": render_next_config(url_prefix),
        "tsconfig.json": render_tsconfig(),
        "postcss.config.mjs": render_postcss_config(),
        "tailwind.config.ts": dt.render_tailwind_config(tokens),
        "components.json": dt.render_components_json(tokens),
        ".gitignore": render_gitignore(),
        "lib/utils.ts": render_lib_utils(),
        "lib/fonts.ts": render_lib_fonts(tokens),
        "app/globals.css": dt.render_globals_css(tokens),
        "app/layout.tsx": render_layout(slug, tokens),
        "app/page.tsx": render_index_page(slug, url_prefix),
        "prism/component_catalog.md": component_catalog.render_full_catalog_markdown(),
    }

    written: list[str] = []
    for rel, content in files.items():
        target = docs.assert_within_project(project_root, Path(docs.PRISM_DIRNAME) / "preview" / rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
        written.append(rel)

    return ScaffoldResult(
        skipped=False,
        preview_dir=preview,
        url_prefix=url_prefix,
        files_written=sorted(written),
    )
