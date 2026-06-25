# Agent Orchestration Layer

A thin, opinionated layer that sits *above* AI agents and decides who does
what, with which tools, under what limits, and what happens when something
goes wrong. Built tier by tier; each tier is independently shippable.

- **Stack:** Python, Anthropic SDK (`claude-opus-4-8`, adaptive thinking).
- **Status:** Tiers 1–2 landed. Tiers 3–6 to follow.

## The six tiers

| Tier | What | Status |
|------|------|--------|
| 1 | Smart routing (dispatch intelligence) | **done** |
| 2 | Least-privilege tool scoping + bounded execution | **done** |
| 3 | Failure isolation at every boundary | planned |
| 4 | Human-in-the-loop confirmation gates | planned |
| 5 | Handoff system (propose, don't chain) | planned |
| 6 | Live hot-reload (config-driven runtime) | planned |

## What's here (Tier 2)

The backbone everything else leans on:

- **`ToolRegistry`** — one source of truth for "what a tool is". Agents never
  hold the registry; they hold a filtered **`ToolView`** (least privilege).
- **`Agent` + `AgentManifest`** — one generic agent class driven by a manifest
  (system prompt, model, tool allowlist, bounds). The manifest *is* the agent,
  which is what Tier 6 will hot-reload from disk.
- **Bounded execution** — `max_iterations` caps the tool-use loop (returns a
  clean "didn't converge" instead of hanging), `max_tokens` bounds each call,
  and each agent declares its own model.

Deliberately **not** here yet: boxing failures as data (Tier 3) and the
confirmation gate (Tier 4). Keeping tier boundaries honest.

## What's here (Tier 1)

The **`Orchestrator`** is the conductor — a router, not a worker:

- Reads a **routing policy built from the agent roster** on every request, so
  adding an agent automatically teaches the conductor about it.
- Enforces four rules: **ownership** (route to the owning agent), **ordering**
  (design/spec before implementation), **decomposition** (a multi-step request
  → an ordered list of separate dispatches), and **clarify-don't-guess** (one
  short question when genuinely ambiguous).
- Routing intelligence lives **only** in the conductor — individual agents
  never learn about each other.

## Quickstart

```bash
pip install -r requirements.txt

# No API key needed — Tier 2 (allowlist) and Tier 1 (policy/isolation) checks:
python demo.py --dry
python demo_routing.py --dry

# Live (needs ANTHROPIC_API_KEY):
export ANTHROPIC_API_KEY=sk-ant-...
python demo.py            # a bounded agent
python demo_routing.py    # routes the four spec scenarios
```

## Design principles

- The orchestrator is a **router, not a worker** — it decides *who* and
  *whether*, then gets out of the way.
- **Least privilege by default** — an agent holds exactly the tools its job
  requires and not one more.
- **Bound everything** — every loop has a max iteration count, every call a
  token ceiling, every agent a declared model.
- **Agents propose, humans dispose** (lands with Tiers 4–5).
