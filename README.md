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
