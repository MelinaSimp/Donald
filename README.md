# Donald

Donald is a tool-using conversational AI assistant.

## Layout

```
src/donald/
  tools/         # BaseTool, ToolRegistry, builtin tools (canonical capability registry)
  integrations.py# external services (Anthropic, OpenAI, SMTP, Tavily)
  subagents/     # specialist personas (researcher, scribe)
  prompt.py      # system-prompt assembly (build_system_prompt)
  cli.py         # `donald` command-line entry point
```

## Development

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest
donald prompt          # print the assembled system prompt
```

## Self-knowledge

Donald maintains a living self-knowledge document at
`context/self/donald.md`. Auto-generated sections are introspected from
the code, and a drift checker keeps the hand-written prose honest.

```bash
donald self-knowledge --render       # print the rendered doc (no write)
donald self-knowledge --refresh      # regenerate AUTO blocks on disk
donald self-knowledge --check        # soft drift report (exit 0)
donald self-knowledge --check --strict   # CI mode (exit non-zero on drift)

bash scripts/install-self-knowledge-hook.sh   # auto-refresh on commit
```

The rendered self-knowledge is injected into the system prompt by
`build_system_prompt` (see `src/donald/prompt.py`). The flavor is
controlled by `--self-knowledge slim|full|none` (or the
`DONALD_SELF_KNOWLEDGE` env var); `slim` is the default.
