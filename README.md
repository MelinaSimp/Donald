# Donald

A Jarvis-style AI assistant you talk to in your terminal. Powered by Claude
(`claude-opus-4-8`).

This is **v0**: a conversational assistant with memory of the current session.
No tools yet — Donald can't touch your files, the web, or your system. That's
the next chapter.

## Setup

```bash
# 1. Install dependencies (a virtualenv is recommended)
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Provide your Anthropic API key
cp .env.example .env      # then edit .env and paste your key
source .env
# (or just: export ANTHROPIC_API_KEY=sk-ant-...)
```

Get a key at <https://console.anthropic.com/>.

## Run

```bash
python donald.py
```

You'll get a prompt. Talk to Donald like you would anyone else.

```
You: what's a good way to structure a python CLI project?
Donald: ...
```

### Commands

| Command  | What it does                          |
| -------- | ------------------------------------- |
| `/help`  | Show the command list                 |
| `/reset` | Forget the conversation, start fresh  |
| `/exit`  | Quit (Ctrl-D / Ctrl-C also work)      |

## Project layout

```
donald.py          # entry point — `python donald.py`
donald/
  cli.py           # the REPL: input loop, streaming, commands
  persona.py       # Donald's system prompt (his voice)
  __init__.py
requirements.txt
.env.example       # copy to .env, add your key
```

## Where this is headed

Donald is built to grow. The natural next steps:

- **Tools** — let Donald run commands, read/write files, search the web. This
  turns him from a chat companion into an agent that can act.
- **Persistent memory** — remember things across sessions, not just within one.
- **Other surfaces** — the same core could sit behind voice or a phone/web
  interface later.

Each of those is a clean addition on top of this core.
