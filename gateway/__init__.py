"""Donald Gateway — the connective tissue of the Donald ("Jarvis") system.

This package is the backend "brain stem" your Claude-designed UI talks to. It
ties three pieces into one connected system:

  * the **Donald brain** — the cocky Claude personality agent in ``donald/``
    (Anthropic, Opus 4.8, with the drift-proof voice layers);
  * **Hermes** — the local NousResearch agent running on your machine, reached
    over its OpenAI-compatible API server (terminal, files, web, memory, skills);
  * the **voice** — ElevenLabs text-to-speech (a Trump-style voice) so Donald
    can talk back.

The UI never talks to Hermes or ElevenLabs directly. It speaks to this gateway
(REST + WebSocket); the gateway routes, applies the repo's security gates, and
streams events back.
"""

from .config import Settings, load_settings

__all__ = ["Settings", "load_settings"]
