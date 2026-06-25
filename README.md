# Agent Factory

A **meta-agent** — the *Factory* — whose only job is to mint *other* sub-agents
on demand. Ask it for "an agent that does X" and it researches what such an
agent needs, drafts its system prompt, picks a tool allowlist from your
catalog, stages a proposed manifest, waits for a human to approve, then
registers it as a first-class, dispatchable agent — **without restarting the
host process.** Think "compiler for sub-agents."

Every spawned agent is **pure configuration**: one generic runtime
([`ConfigDrivenAgent`](agent_factory/runtime.py)) reads a row from the
`spawned_agents` table and runs a vanilla tool-use loop. There is **no bespoke
class per agent** — that is the single most important constraint here.

## Stack (as chosen at build time)

| Concern | Choice |
|---|---|
| Language | Python 3.10+ |
| Schemas | Pydantic v2 (`SkillsReport`, `ProposedManifest`, row models) |
| LLM provider | Anthropic official SDK (reused for research, prompt-gen, and spawned agents) |
| Database | SQLite (stdlib) with a tiny SQL-file migration runner |
| Approval surface | CLI |
| Web search | Pluggable `SearchBackend` (Null by default; bring your own provider) |

Greenfield defaults: reserved slugs `factory, forge, admin, system, root`;
daily cap **5** spawn tasks/user/day; **3** revision rounds; hard binary
approval (approved → live). All overridable via env vars (see
[`config.py`](agent_factory/config.py)).

## Install & quickstart

```bash
pip install -e .          # or: pip install pydantic anthropic
export ANTHROPIC_API_KEY=sk-...   # needed for LLM-driven commands

factory init-db
factory spawn --name "Doc Summarizer" \
    --role "summarizes long documents into concise bullet points" --by alice
factory run-pipeline <task_id>      # researches, drafts spec + prompt, stages manifest
factory pending                     # review what's awaiting approval (+ manifests)
factory approve <task_id>           # registers dispatch_to_doc_summarizer, no restart
factory dispatch doc_summarizer "Summarize this: ..."
```

`run-pipeline` executes **synchronously to completion**, so there is no
fire-and-forget background task that could be garbage-collected mid-run (the
asyncio weak-reference hazard called out in the brief does not apply to this
surface). When you add a web/async surface, hold a strong reference to any
`asyncio.create_task(...)` you spawn.

## Architecture — five tiers

```
PENDING → RESEARCHING → DRAFTING_SPEC → WRITING_PROMPT → AWAITING_APPROVAL → APPROVED
   (any non-terminal state can fall to FAILED; AWAITING_APPROVAL can roll back
    to WRITING_PROMPT on reject-with-feedback, or end at REJECTED)
```

Transitions are a dict-of-sets in [`models.py`](agent_factory/models.py) and
enforced at the repo layer — illegal transitions raise `InvalidTransition`,
they never happen silently.

| Tier | What it does | Code |
|---|---|---|
| 1 | Research subagent → JSON-validated `SkillsReport` (24h cache; **forced** `emit_skills_report` on the last loop turn) | [`research.py`](agent_factory/research.py) |
| 2 | Spec markdown + system-prompt generation (with injection sanitization) | [`spec.py`](agent_factory/spec.py) |
| 3 | The spawn pipeline state machine; any exception lands the task in `FAILED` | [`pipeline.py`](agent_factory/pipeline.py) |
| 4 | Approval gate: approve / reject-with-feedback (regenerates **only** the prompt) / reject; `get_pending` hydration | [`approval.py`](agent_factory/approval.py) |
| 5 | `ConfigDrivenAgent` runtime + `RegistryWatcher` hot-reload | [`runtime.py`](agent_factory/runtime.py) |

### Tables

- `research_reports` — cached Skills Reports (24h dedup on normalized query)
- `spawn_tasks` — in-flight pipeline state, proposed manifest, revision feedback
- `spawned_agents` — the registered agents (pure config; `slug` is `UNIQUE`)

Every `spawned_agents` row keeps `created_by_task_id`, so any running agent
traces back to the request, the Skills Report, the revision feedback, and the
approval that produced it.

## Safety guardrails (built in, not optional)

- **`factory_allowed` flag** on every tool. The Factory only offers
  `factory_allowed=True` tools to spawned agents. The starter catalog ships
  `read_env` and `send_email` as `factory_allowed=False` to demonstrate the
  internal-only opt-out for secrets-bearing / outward-facing tools.
- **Reserved slugs** are refused *before* any LLM work (cheap, clean error),
  and the DB `UNIQUE` constraint is the backstop.
- **Daily cap** enforced at task *creation*, not approval — an attacker can't
  queue thousands of tasks even though approvals are gated.
- **Prompt-injection containment** ([`sanitize.py`](agent_factory/sanitize.py)):
  user `role_description` / `special_requirements` are scanned (task refused on
  match) and sanitized before being inlined; the generated system prompt is
  checked to ensure it *paraphrased* rather than copied user input verbatim.

## Approval surface notes

- `factory pending` is the **page-load / reconnect hydration** equivalent — it
  returns every `awaiting_approval` task with its manifest. A push-only
  notification would leave a refreshed UI showing nothing; always pair pushes
  with this poll.
- The `agent_added` event carries `created_by_task_id` so a list-based UI can
  clear the right pending row.

## Plugging in real web search

The default `NullSearchBackend` returns nothing (research still completes via
the forced final emit). Implement `SearchBackend.search` against your provider
(Tavily, Serper, Brave, or Anthropic's native `web_search_20250305`) and pass
it to `build_default_registry(...)` and `run_research(...)`. See
[`search.py`](agent_factory/search.py).

## Tests

```bash
pip install pytest
pytest -q
```

The suite drives the **entire** pipeline with a `FakeLLMClient` and a
`StaticSearchBackend`, so it runs offline with no API key: state machine,
sanitization, research (incl. cache hit), full pipeline → approval → hot-reload
→ dispatch, reserved-slug + daily-cap + injection refusals, and the revision cap.

## Extending to a web (FastAPI) surface

The approve/reject/pending functions in `approval.py` are plain functions that
take repos + an event sink — wrap them in FastAPI routes, swap `LoggingEventSink`
for a WebSocket broadcaster, and run `RegistryWatcher.start_polling()` (or wire
SQLite/Postgres change detection) on startup. The Factory itself is just one
more sub-agent; only its *outputs* are persistent, runnable agents.
```
