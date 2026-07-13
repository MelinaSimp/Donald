# Donald

A **personal AI OS** — a desktop app backed by an agent with persistent memory and
a wide set of integrations. A personal AI team that remembers you, adapts, and acts
on your behalf across sessions.

## Start here

| Doc | What it covers |
|-----|----------------|
| **[PRODUCT.md](./PRODUCT.md)** | What Donald is — the four systems, the code spine, the honest state of things. |
| **[DISTRIBUTION_ROADMAP.md](./DISTRIBUTION_ROADMAP.md)** | How we get to a shippable, distributable product — milestones M0–M7. |
| [archive/README.md](./archive/README.md) | Parallel experiments moved off the build path during consolidation. |

## The spine

| Module | Role |
|--------|------|
| [`donald/`](./donald) | The agent core (loop, brain, memory, safety, voice, proactive daemon). |
| [`orchestrator/`](./orchestrator) | Routing + the six-tier framework — see its [README](./orchestrator/README.md). |
| [`gateway/`](./gateway) | Model-agnostic HTTP/WebSocket server that streams agent events to the UI. |
| [`web/`](./web) | Next.js UI — seed for the marketing site and desktop shell. |

## Quickstart

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
python donald.py            # run the agent
```

- **Stack:** Python + Anthropic SDK (`claude-opus-4-8`), model-agnostic via the gateway.
- **Status:** Agent core is the most complete piece; the product shell (desktop
  app, multi-user backend, billing, signing) is the work ahead — see the roadmap.

> **Note:** the agent core is mid-consolidation onto one canonical `donald`
> package; until that lands, some tests are red at collection. See the roadmap's
> M0 section.
