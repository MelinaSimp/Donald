"""A small, opinionated orchestration layer for AI agents.

Tier 2 (this PR): a shared tool registry + a generic, config-driven agent that
runs a bounded, least-privilege tool-use loop. Later tiers (routing, failure
isolation, confirmation gates, handoffs, hot-reload) build on this backbone.
"""

from .agent import Agent, AgentManifest, AgentResult
from .llm import LLM, DEFAULT_MODEL
from .orchestrator import Orchestrator, RoutingDecision, RouteStep
from .registry import Tool, ToolRegistry, ToolView
from .tools import build_default_registry

__all__ = [
    "Agent",
    "AgentManifest",
    "AgentResult",
    "LLM",
    "DEFAULT_MODEL",
    "Orchestrator",
    "RoutingDecision",
    "RouteStep",
    "Tool",
    "ToolRegistry",
    "ToolView",
    "build_default_registry",
]
