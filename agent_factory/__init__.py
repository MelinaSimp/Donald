"""Agent Factory — a meta-agent that mints other sub-agents on demand.

The Factory researches what a requested specialist should do, drafts its
system prompt, picks a tool allowlist from the host catalog, stages a
proposed manifest for human approval, and — once approved — registers it as
a first-class, dispatchable agent without restarting the host process.

Every spawned agent is *pure configuration*: one generic runtime
(:class:`agent_factory.runtime.ConfigDrivenAgent`) reads a row from the
``spawned_agents`` table and runs a vanilla tool-use loop. There is no
bespoke class per agent — that is the single most important constraint in
the architecture.
"""

__all__ = ["__version__"]
__version__ = "0.1.0"
