# Donald

A Jarvis-style AI assistant you talk to in your terminal. Powered by Claude
(`claude-opus-4-8`).

Donald is an **agent**: he holds a conversation, and when it helps, he reaches
for tools — reading, writing, and editing files, running shell commands, and
searching the web — then reports back. He **remembers** durable facts about you
between sessions, and can optionally **speak** his replies.

## Setup

```bash
# 1. Install (a virtualenv is recommended)
python3 -m venv .venv && source .venv/bin/activate
pip install -e .              # core
# pip install -e '.[voice]'   # optional: spoken replies + spoken input
# pip install -e '.[dev]'     # optional: pytest

# 2. Provide your Anthropic API key
cp .env.example .env          # then edit .env and paste your key
source .env
# (or just: export ANTHROPIC_API_KEY=sk-ant-...)
```

Get a key at <https://console.anthropic.com/>.

## Run

```bash
donald            # installed console command
# or, without installing:
python donald.py
```

You'll get a prompt. Talk to Donald like you would anyone else.

```
You: what's in requirements.txt, and is the anthropic version current?
You: edit hello.py to print the time instead of "hi", then run it
You: search for the latest claude model and tell me its context window
You: remember that I prefer terse answers
```

### Commands

| Command   | What it does                                  |
| --------- | --------------------------------------------- |
| `/help`   | Show the command list                         |
| `/reset`  | Forget the current conversation, start fresh  |
| `/memory` | Show what Donald remembers across sessions    |
| `/forget` | Wipe Donald's long-term memory                |
| `/voice`  | Toggle spoken replies (needs the `voice` extra) |
| `/listen` | Speak one message instead of typing it        |
| `/exit`   | Quit (Ctrl-D / Ctrl-C also work)              |

## Tools & safety

| Tool            | What it does                                   | Approval?        |
| --------------- | ---------------------------------------------- | ---------------- |
| `read_file`     | Read a text file in the working directory      | Auto (read-only) |
| `write_file`    | Create/overwrite a whole file                  | **Asks first**   |
| `edit_file`     | Replace an exact snippet in a file (surgical)  | **Asks first**   |
| `run_shell`     | Run a shell command                            | **Asks first**¹  |
| `web_search`    | Search the web for current info                | Auto             |
| `remember`      | Save a durable fact to long-term memory        | Auto (own notes) |
| `update_memory` | Rewrite/curate the whole memory set            | Auto (own notes) |

¹ unless the command matches your `shell_auto_approve` allowlist (see below).

Safety guards:

- **Approval gates.** Anything that can change your machine (`write_file`,
  `edit_file`, `run_shell`) shows you the exact action and waits for `y` before
  running. Decline and Donald adapts.
- **Sandboxed file access.** File reads and edits are confined to the directory
  you launched Donald from. Paths that try to escape it (via `..` or an absolute
  path) are rejected.

> Donald runs whatever shell command you approve. Approve deliberately, and run
> him from the directory you actually want him working in.

## Memory

Donald keeps durable facts in `~/.donald/memory.md`, loaded into his system
prompt at the start of each session. He adds to it with `remember` and tidies it
with `update_memory` (which backs up the prior copy to `memory.bak`). Review it
with `/memory`, wipe it with `/forget`.

## Configuration

Optional. Settings come from defaults, then `~/.donald/config.json`, then
environment variables (later wins). All keys are optional.

```json
{
  "model": "claude-opus-4-8",
  "max_tokens": 4096,
  "shell_timeout_s": 60,
  "max_output_chars": 100000,
  "shell_auto_approve": ["git status", "ls", "cat"],
  "voice": false
}
```

- `shell_auto_approve` — command **prefixes** that run without asking. Use it for
  safe, read-only commands you trust; everything else still prompts.
- Env overrides: `DONALD_MODEL`, `DONALD_MAX_TOKENS`, `DONALD_SHELL_TIMEOUT`,
  `DONALD_MAX_OUTPUT_CHARS`, `DONALD_SHELL_AUTO_APPROVE` (comma-separated),
  `DONALD_VOICE`.

## Voice (optional)

Install the extra (`pip install -e '.[voice]'`) for spoken replies and input.
Microphone capture also needs a system PortAudio library
(`brew install portaudio` on macOS, `apt install portaudio19-dev` on Debian).

- Start with `donald --voice`, or toggle in-session with `/voice`.
- Say one message with `/listen`.

Without the extra (or on a headless machine) voice simply prints a hint and
Donald keeps working as normal.

## Project layout

```
donald.py          # entry point — `python donald.py`
pyproject.toml     # packaging, `donald` console command, extras
donald/
  cli.py           # the REPL: input loop, streaming, agent loop, commands
  tools.py         # tool definitions, executors, path/approval guards
  memory.py        # long-term memory (~/.donald/memory.md)
  config.py        # settings: defaults < config.json < env
  voice.py         # optional TTS/STT layer
  persona.py       # Donald's system prompt (his voice)
  __init__.py
tests/             # pytest suite
.env.example       # copy to .env, add your key
```

## Tests

```bash
pip install -e '.[dev]'
pytest
```
# Agent Orchestration Layer

A thin, opinionated layer that sits *above* AI agents and decides who does
what, with which tools, under what limits, and what happens when something
goes wrong. Built tier by tier; each tier is independently shippable.

- **Stack:** Python, Anthropic SDK (`claude-opus-4-8`, adaptive thinking).
- **Status:** All six tiers landed.

## The six tiers

| Tier | What | Status |
|------|------|--------|
| 1 | Smart routing (dispatch intelligence) | **done** |
| 2 | Least-privilege tool scoping + bounded execution | **done** |
| 3 | Failure isolation at every boundary | **done** |
| 4 | Human-in-the-loop confirmation gates | **done** |
| 5 | Handoff system (propose, don't chain) | **done** |
| 6 | Live hot-reload (config-driven runtime) | **done** |

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

## What's here (Tier 3)

Errors cross every boundary as **values, not exceptions** — one failure never
takes down the run:

- **Tool boundary** — a throwing handler or an out-of-scope tool name becomes a
  structured `{"error": ...}` tool_result the model can read and react to.
- **Sub-agent boundary** — the orchestrator boxes a crashing agent into a
  human-friendly `AgentResult` (+ a short error string for logs) and keeps
  going.
- **Observer boundary** — `EventEmitter` fans events to fire-and-forget hooks
  (UI/logs/analytics); a throwing hook is swallowed so a broken dashboard can't
  block real work.

Each boundary logs the contained failure, so it's still visible to operators.

## What's here (Tier 4)

Destructive/irreversible actions stop and ask first — and the gate lives in the
**router**, not in the tools:

- A tool marked `requires_confirmation` is **not executed** when called; the
  router surfaces a structured `confirmation_required` payload (tool + inputs)
  to an **approver** and waits.
- Only an explicit approval runs the action, via a separate execute-confirmed
  path (`Agent.execute_confirmed`).
- The default approver is **`DenyAll`** (fail-safe). Swap in `AllowAll`,
  `CallbackApprover` (policy/UI hook), or `ConsoleApprover` (interactive y/N).

## What's here (Tier 5)

Agents **propose** the next edge of the work graph; the human approves it. No
agent dispatches another directly:

- An agent that may hand off has the `propose_handoff` control tool in its
  allowlist (handoff capability is itself least-privilege). The agent loop
  intercepts it and records a typed `HandoffRecommendation` —
  `target_agent`, `reason`, `task`, `artifacts` (references only),
  `preconditions`, `confidence` — without dispatching anything.
- The orchestrator surfaces it as a conversational offer (`offer`) and waits;
  `review_handoff` dispatches **only** on explicit approval. The default
  `HoldForHuman` approver never auto-accepts.
- Artifacts must be references (paths/IDs/URLs); inlined blobs are rejected, so
  handoffs stay small and serializable.

## What's here (Tier 6)

Agents are **data**, so the roster can change while the process runs:

- **`ManifestStore`** — one JSON file per agent in a directory is the source of
  truth (`"active": false` retires one without deleting it).
- **`AgentRuntime`** — keeps the live roster in sync with a manifest set and
  maintains a `dispatch_to_<name>` tool per agent (capability and definition
  decoupled).
- **`ManifestWatcher.poll()`** — the change signal: on a file-watch event or an
  interval, it reloads and applies the diff (new agents register, retired ones
  unregister). A bad manifest is skipped, not fatal. No restart, no redeploy.

```python
from orchestrator import (
    AgentRuntime, ManifestStore, ManifestWatcher, build_default_registry,
    serve, serve_with_watchdog,
)

runtime = AgentRuntime(build_default_registry())
watcher = ManifestWatcher(ManifestStore("./agents"), runtime)

watcher.poll()                       # one-shot: apply the current manifest set
serve(watcher, interval=1.0)         # interval polling (no extra dependency)
serve_with_watchdog(watcher)         # push-based on FS events (pip install watchdog)
```

## Quickstart

```bash
pip install -r requirements.txt

# No API key needed — each demo verifies one tier's invariants:
python demo.py --dry
python demo_routing.py --dry
python demo_isolation.py
python demo_confirm.py
python demo_handoff.py
python demo_runtime.py
python demo_live_roster.py   # end-to-end: routing over a hot-reloaded roster

# Live (needs ANTHROPIC_API_KEY):
export ANTHROPIC_API_KEY=sk-ant-...
python demo.py            # a bounded agent
python demo_routing.py    # routes the four spec scenarios
```

## Tests

A CI-friendly pytest suite covers every tier's invariants with no API key
(the agent loop is driven by scripted fake LLMs):

```bash
pip install -r requirements-dev.txt
pytest
```

## Design principles

- The orchestrator is a **router, not a worker** — it decides *who* and
  *whether*, then gets out of the way.
- **Least privilege by default** — an agent holds exactly the tools its job
  requires and not one more.
- **Bound everything** — every loop has a max iteration count, every call a
  token ceiling, every agent a declared model.
- **Agents propose, humans dispose** — anything consequential (Tier 4 gates,
  Tier 5 handoffs) stops and asks; the human is the circuit-breaker.
- **Pass references, not payloads** — handoffs carry paths/IDs/URLs, not blobs.

## How the tiers fit together

- The **shared registry** (Tier 2) is what **Tier 1** routes over, what agents
  filter into **allowlists**, and what **Tier 6** registers dispatch tools into
  at runtime.
- **Failure isolation** (Tier 3) is what makes **Tier 5** handoffs and **Tier 6**
  dynamic agents safe to run — a bad agent (or a bad manifest) fails in its box.
- **Confirmation gates** (Tier 4) and **handoff approvals** (Tier 5) are the same
  idea at two levels: nothing consequential happens without a human yes.
- **Routing + hot-reload meet** in a hot-reloadable conductor: point a
  `ManifestWatcher` at the `Orchestrator` and its routing roster reloads from
  disk live (`demo_live_roster.py`). Dispatch still flows through the conductor,
  never agent-to-agent — Tier 5's no-silent-chaining rule holds.

## Module map

| Module | Tier | Role |
|--------|------|------|
| `registry.py` | 2 | `ToolRegistry` + filtered `ToolView` (least privilege) |
| `agent.py` | 2/3/4/5 | bounded loop; tool boundary; confirmation gate; handoff capture |
| `llm.py` | — | thin Anthropic Messages API wrapper (adaptive thinking) |
| `orchestrator.py` | 1/5 | the conductor: routing + handoff review |
| `events.py` | 3 | fire-and-forget observer bus |
| `confirmation.py` | 4 | `Approver` seam + built-ins |
| `handoff.py` | 5 | `HandoffRecommendation`, `propose_handoff` control tool |
| `runtime.py` | 6 | manifest store + watcher + dispatch-tool factory |
