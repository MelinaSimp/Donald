"""Wren — a voice-first personal assistant.

Five parts wired together (see AGENT.md):
  brain  -> agent.py + llm.py
  hands  -> tools/
  ears/mouth -> voice/
  memory -> memory.py
  heartbeat -> heartbeat.py
  rails  -> safety.py

One shared agent core, many ways in and out.
"""

__version__ = "0.1.0"
