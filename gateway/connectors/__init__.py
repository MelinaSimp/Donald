"""Pluggable connectors — the adapter layer.

``Hermes`` is one connector today; the ``AgentConnector`` protocol is the seam
so a different local agent can be dropped in without touching the orchestrator.
"""

from .base import AgentConnector, ConnectorError, ConnectorResult
from .hermes import HermesConnector
from .voice import ElevenLabsVoice, VoiceResult

__all__ = [
    "AgentConnector",
    "ConnectorError",
    "ConnectorResult",
    "HermesConnector",
    "ElevenLabsVoice",
    "VoiceResult",
]
