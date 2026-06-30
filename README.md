# Donald — Prism head-of-design agent

**Prism** is a head-of-design sub-agent. Dispatch it a design task
("design the hero") and it ships an actually-good Next.js + Tailwind + shadcn
screen: real Google Fonts, composed components (shadcn / MagicUI), AI-generated
atmospheric imagery, and live animations.

The core idea: **award-winning design is composed from high-quality primitives,
not authored from scratch.** Asking a model to "write HTML" has a hard quality
ceiling. So Prism plans cheaply (Sonnet), then spawns **Claude Code** to compose
a real component framework into a per-project preview app.

## Architecture (by tier)

| Module | Tier | Responsibility |
|---|---|---|
| `prism/config.py` | 0 | Settings, model defaults, key presence, cost caps |
| `prism/docs.py` | 1 | Three-document model: slug→path registry, containment, read/write |
| `prism/design_tokens.py` | 1 | Parse/validate the ` ```yaml tokens ` block; render Tailwind + globals.css + shadcn config |
| `prism/fonts.py` | 1/4 | Curated Google Fonts catalog + `FORBIDDEN_FAMILIES` |
| `prism/bootstrap.py` | 1 | First-dispatch **concrete** `design.md` + `brief.md` from a repo scan |
| `prism/component_catalog.py` | 4 | Curated component palette (shadcn / MagicUI / Framer Motion) |
| `prism/scaffold.py` | 2 | The per-project Next.js preview app (~13 files), idempotent |
| `prism/claude_code_runner.py` | 3 | Spawn Claude Code as a subprocess; sanitized env; NDJSON stream |
| `prism/prompts.py` | 3/6/7 | System prompt (BRIEF IS LAW + required visual elements) + the CC `-p` prompt |
| `prism/references.py` | 7 | Path-safe reference-image validation |
| `prism/image_gen.py` | 5 | Gemini image generation → `public/assets`, returns full basePath URL |
| `prism/audit.py` | 6 | Audit the rendered TSX (install ≠ use) for the required elements |
| `prism/tools.py` | 3/5 | `generate_mockup` + `generate_image` schemas and execute branches |
| `prism/agent.py` | — | The cheap planning loop (Anthropic SDK, lazy) + testable tool router |
| `prism/orchestrator.py` | — | Minimal dispatch harness (bootstrap → scaffold → plan → compose) |
| `prism/serving.py` | 2/5 | FastAPI endpoint serving each project's static `out/` export |

### The three-document model

```
<project>/
  design.md                 # PUBLIC, STABLE   — design system (yaml tokens block)
  .prism/
    brief.md                # PRIVATE, EVOLVING — strategic memory; THE BRIEF IS LAW
    references/<feature>/    # reference screenshots (Tier 7)
    preview/                # the Next.js preview app (Tier 2); out/ is served
  features/<feature>.md     # PUBLIC, RAPIDLY EVOLVING — per-feature spec
```

## Dependencies are optional by design

The package imports and **all unit ship-tests pass with zero API keys and none
of the live packages installed**. Each integration is imported lazily; only the
live call path that needs a dependency raises (with a clear message).

```bash
pip install -e .            # core only (pyyaml)
pip install -e '.[agent]'   # + anthropic            (planning loop)
pip install -e '.[images]'  # + google-genai         (Tier 5; needs billing)
pip install -e '.[serving]' # + fastapi/uvicorn       (serve mockups)
```

Configure via `.env` (see `.env.example`): `ANTHROPIC_API_KEY` (planning +
Claude Code), `GEMINI_API_KEY` (images — **not** in Gemini's free tier),
`PRISM_PROJECTS_BASE` or `PRISM_REGISTRY` (project resolution).

## Usage

```bash
prism bootstrap my-app --path /abs/path/to/my-app   # concrete design.md + brief.md
prism scaffold  my-app                              # the Next.js preview app
prism dispatch  my-app "design the marketing hero"  # plan + compose (needs keys)
prism serve                                         # serve /api/<slug>/preview/...
```

## Tests

```bash
python -m pytest          # 55 tests, no network/keys required
```

Each tier has a ship test (`tests/test_tier*.py`). The composer and image-gen
tests inject a fake subprocess / stub client, so the full pipeline is exercised
without a `claude` binary or a Gemini key.

## Known guardrails (the anti-patterns this build encodes)

- **Substrate caps the ceiling** — composes a real framework, never vanilla HTML.
- **THE BRIEF IS LAW** — a system-prompt section; voice cues never silently
  override the brief.
- **Restrained brief = restrained output** — the bootstrap brief commits *toward*
  richness (visible texture ≥ 0.4, continuous motion, product surface).
- **Install ≠ use** — `audit.py` checks the rendered TSX, not the install log.
- **basePath on plain `<img>`** — `image_gen` returns the full prefixed URL.
- **Static export layout** — `trailingSlash: true` → `out/<path>/index.html`.
