# Donald

A cocky, comedic personality agent — a parody bombast who's the biggest ego in
any room, with a **personality-persistence layer** that stops the voice from
drifting into generic-assistant mode over a long conversation.

## The problem it solves

A strong personality prompt wins turn one, then slowly flattens. By turn ten
the agent is saying *"Great question, let me help you with that."* This isn't a
prompt-quality bug — it's positional. As the chat grows, the assistant's own
prior turns become the strongest behavioral signal and outweigh the cached
personality block at the top. The fix is to reinforce the voice from **both
ends** of the context window.

## The four layers

```
System prompt (cached) ........ AGENT.md — rules + concrete voice examples
System prompt (uncached) ...... tonal checkpoint, refreshed every turn
Conversation history .......... clean user/assistant turns (no cue)
LAST user message (API only) .. voice cue — sits AFTER all prior turns
```

The **voice cue** is load-bearing: it rides on the last user message of the API
payload only (never stored), so it sits after every prior assistant turn — the
position the model attends to most. The other layers reinforce it.

## Layout

| File | Role |
|------|------|
| `donald/AGENT.md` | The personality: voice examples, "never sound like" list, needle topics, guardrails |
| `donald/personality.py` | `append_voice_cue`, `build_system_prompt`, the cue + checkpoint strings |
| `donald/conversation.py` | `ConversationManager` — stores clean history, hands out mutable API copies |
| `donald/agent.py` | The turn loop wiring it all into an Anthropic API call |
| `tests/test_personality.py` | Structural tests for the wiring |

## Run it

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-...
python -m donald.agent
```

## Test it

```bash
pip install -r requirements.txt
pytest
```

## Tuning

Still drifting generic? Add more examples to the cue (recency wins), keep the
checkpoint firing every turn, nudge temperature up. Going too mean? The
"affectionate roast, never genuinely cruel" line in the cue is the floor —
keep it literally present. The guardrails in `AGENT.md` keep the parody from
tipping into real-world hate or politics.

> This is a comedy character. The bragging and roasting are the bit; the
> guardrails in `AGENT.md` are not optional.
