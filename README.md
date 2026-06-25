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
the code on every commit, and a drift checker keeps the hand-written
prose honest. See the `donald self-knowledge` subcommands.
