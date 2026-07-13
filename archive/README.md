# Archive

Parallel experiments and superseded skeletons moved out of the active tree during
the **M0 consolidation** (see `../DISTRIBUTION_ROADMAP.md`). Nothing here is on the
product's build path. History is preserved — everything was moved with `git mv`,
so `git log --follow` still works, and anything here can be restored if needed.

| Path | What it was | Why archived |
|------|-------------|--------------|
| `trillion/` | `src/trillion` — a parallel agent/tool skeleton | Superseded by the canonical `donald/` agent core |
| `prism/` | "Prism" head-of-design sub-agent (Next.js mockups) | A separate capability, not the product shell; can return later as a sub-agent |
| `agent_factory/` | Agent-spawning / research-loop experiment | Parallel skeleton, not the chosen spine |
| `wren/` | The predecessor voice assistant — most integrations actually built (Gmail/Calendar/Drive, MCP client, computer-control) + its `AGENT.md` | Superseded by `donald/`; **harvest its integrations** during roadmap M4 |
| `src-donald/` | The `src/donald` tool **framework** — `BaseTool`/`ToolRegistry`, subagents, self-knowledge (self-documenting), integrations, prompt-builder | A second `donald` package that collided with the canonical one; **harvest its framework** during the agent-core reconciliation |
| `aether-orb/` | The "aether-cosmic-interface" three.js voice orb (`index.html`, `scene.js`, `js/`, `client/`, root `package.json`) | Marketing/desktop UI now seeds from `web/` (Next.js); the three.js orb was a separate UI experiment |
| `north-star.md` | "Drift AI" CRE north-star (Hermes/Dante/Vault) | A different product framing; the active product is Donald (`PRODUCT.md`) |
| `tests/`, `tests-unit/` | Tests belonging to the modules above | Moved with their code so the active suite stays coherent |

The active product spine is: `donald/` (agent core) · `orchestrator/` (routing/tier
framework) · `gateway/` (model-agnostic streaming server) · `web/` (UI seed).
