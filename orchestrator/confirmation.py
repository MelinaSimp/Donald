"""Confirmation gates — Tier 4's human-in-the-loop.

A destructive or irreversible tool (one marked `requires_confirmation`) is not
executed when called. The router surfaces a structured request to an *approver*
— the seam where a human decides — and only an explicit approval lets the
separate execute-confirmed path run the action.

The default approver is `DenyAll`: fail-safe. If a gated tool is reached with no
approver wired in, it does not run.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol, runtime_checkable


@dataclass(frozen=True)
class ConfirmationRequest:
    """The structured `confirmation_required` payload shown to the human."""

    agent: str
    tool: str
    tool_input: dict[str, Any]


@dataclass(frozen=True)
class ConfirmationDecision:
    approved: bool
    reason: str = ""


@runtime_checkable
class Approver(Protocol):
    def decide(self, request: ConfirmationRequest) -> ConfirmationDecision: ...


class DenyAll:
    """Fail-safe default — nothing gated runs without an explicit approver."""

    def decide(self, request: ConfirmationRequest) -> ConfirmationDecision:
        return ConfirmationDecision(False, "denied by default (no approver configured)")


class AllowAll:
    """Auto-approve everything. For tests or trusted, non-interactive runs only."""

    def decide(self, request: ConfirmationRequest) -> ConfirmationDecision:
        return ConfirmationDecision(True, "auto-approved")


@dataclass
class CallbackApprover:
    """Delegate the yes/no to any predicate — a UI hook, a policy, a test."""

    fn: Callable[[ConfirmationRequest], bool]

    def decide(self, request: ConfirmationRequest) -> ConfirmationDecision:
        ok = bool(self.fn(request))
        return ConfirmationDecision(ok, "approved" if ok else "denied")


class ConsoleApprover:
    """Surface the request on the terminal and block on a y/N answer."""

    def decide(self, request: ConfirmationRequest) -> ConfirmationDecision:
        print(
            f"\n[confirmation required] agent {request.agent!r} wants to run "
            f"{request.tool!r} with input {request.tool_input!r}"
        )
        answer = input("approve? [y/N] ").strip().lower()
        ok = answer in ("y", "yes")
        return ConfirmationDecision(ok, "approved by user" if ok else "denied by user")
