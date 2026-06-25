# Donald

A Jarvis-style AI assistant you talk to in your terminal. Powered by Claude
(`claude-opus-4-8`).

Donald is an **agent**: he holds a conversation, and when it helps, he reaches
for tools — reading files, writing files, running shell commands, and searching
the web — then reports back. Memory is per-session for now.

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

Try things like:

```
You: what's in requirements.txt, and is the anthropic version current?
You: write a hello.py that prints the time, then run it
You: search for the latest claude model and tell me its context window
```

### Commands

| Command  | What it does                          |
| -------- | ------------------------------------- |
| `/help`  | Show the command list                 |
| `/reset` | Forget the conversation, start fresh  |
| `/exit`  | Quit (Ctrl-D / Ctrl-C also work)      |

## Tools & safety

Donald has four tools:

| Tool          | What it does                              | Approval?        |
| ------------- | ----------------------------------------- | ---------------- |
| `read_file`   | Read a text file in the working directory | Auto (read-only) |
| `write_file`  | Create/overwrite a file                   | **Asks first**   |
| `run_shell`   | Run a shell command                       | **Asks first**   |
| `web_search`  | Search the web for current info           | Auto             |

Safety guards:

- **Approval gates.** Anything that can change your machine (`write_file`,
  `run_shell`) shows you the exact action and waits for `y` before running.
  Decline and Donald adapts.
- **Sandboxed file access.** File reads and writes are confined to the
  directory you launched Donald from. Paths that try to escape it (via `..` or
  an absolute path) are rejected.

> Donald runs whatever shell command you approve. Approve deliberately, and run
> him from the directory you actually want him working in.

## Project layout

```
donald.py          # entry point — `python donald.py`
donald/
  cli.py           # the REPL: input loop, streaming, agent loop, commands
  tools.py         # tool definitions, executors, path/approval guards
  persona.py       # Donald's system prompt (his voice)
  __init__.py
requirements.txt
.env.example       # copy to .env, add your key
```

## Where this is headed

Donald is built to grow. The natural next steps:

- **Persistent memory** — remember things across sessions, not just within one.
- **More tools** — whatever your workflow needs (git helpers, notes, calendars).
- **Other surfaces** — the same agent core could sit behind voice or a
  phone/web interface. And once Donald's tools are ones that *only* run on your
  laptop, a cloud/local bridge could let you trigger them from anywhere.

Each of those is a clean addition on top of this core.
