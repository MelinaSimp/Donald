"""Tier 4 — the approval gate (human-in-the-loop).

A proposed manifest sits in ``awaiting_approval`` until a human acts:

* **approve** -> insert a ``spawned_agents`` row, flip the task to
  ``APPROVED``, notify the registry so the agent becomes dispatchable, and
  emit ``agent_added`` (carrying ``created_by_task_id`` so a list UI can
  clear the right pending row).
* **reject with feedback** -> store the feedback, increment the iteration
  count, roll back to ``WRITING_PROMPT``, and regenerate *only* the system
  prompt (research and spec are already cached — don't burn the budget).
  Past the configured cap the task auto-fails.
* **reject with no feedback** -> terminal ``REJECTED``.

:func:`get_pending` is the page-load / reconnect hydration endpoint: it
returns every ``awaiting_approval`` task with its manifest. Without this, a
reviewer who refreshes sees nothing even when agents are waiting.
"""

from __future__ import annotations

from typing import Callable, Optional

from agent_factory.config import Config
from agent_factory.events import EventSink
from agent_factory.llm import LLMClient
from agent_factory.models import SpawnedAgent, SpawnTask, State
from agent_factory.repos import (
    ResearchReportRepo,
    SpawnedAgentRepo,
    SpawnTaskRepo,
    new_agent_id,
    now_iso,
)
from agent_factory.spec import generate_system_prompt

# Called after an agent is saved so the watcher can register its dispatch tool.
NotifyRegistry = Callable[[str], None]


class NotApprovable(Exception):
    pass


def get_pending(tasks_repo: SpawnTaskRepo) -> list[dict]:
    """Hydration endpoint: all awaiting_approval tasks + their manifests."""
    pending: list[dict] = []
    for task in tasks_repo.list_by_status(State.AWAITING_APPROVAL):
        pending.append(
            {
                "task_id": task.id,
                "name": task.name_hint,
                "requested_by": task.requested_by,
                "approval_iterations": task.approval_iterations,
                "manifest": task.proposed_manifest.model_dump()
                if task.proposed_manifest
                else None,
            }
        )
    return pending


def handle_approve(
    *,
    task_id: str,
    tasks_repo: SpawnTaskRepo,
    agents_repo: SpawnedAgentRepo,
    emit_event: EventSink,
    notify_registry: Optional[NotifyRegistry] = None,
) -> SpawnedAgent:
    task = tasks_repo.get(task_id)
    if task is None:
        raise NotApprovable(f"no such task: {task_id}")
    if task.status != State.AWAITING_APPROVAL:
        raise NotApprovable(
            f"task {task_id} is {task.status.value}, not awaiting_approval"
        )
    manifest = task.proposed_manifest
    if manifest is None:
        raise NotApprovable("task has no proposed manifest")

    agent = SpawnedAgent(
        id=new_agent_id(),
        slug=manifest.slug,
        name=manifest.name,
        specialty=manifest.specialty,
        system_prompt=manifest.system_prompt,
        tool_allowlist=manifest.tool_allowlist,
        model=manifest.model,
        status="active",
        created_by_task_id=task_id,
        created_at=now_iso(),
    )
    saved = agents_repo.save(agent)
    tasks_repo.transition(task_id, State.APPROVED)

    if notify_registry is not None:
        notify_registry(saved.slug)

    emit_event(
        kind="agent_added",
        event={
            "slug": saved.slug,
            "name": saved.name,
            # Row key for the approval surface — without it the UI can't tell
            # which pending card just resolved.
            "created_by_task_id": task_id,
        },
    )
    return saved


def handle_reject(
    *,
    task_id: str,
    tasks_repo: SpawnTaskRepo,
    reports_repo: ResearchReportRepo,
    config: Config,
    llm: LLMClient,
    emit_event: EventSink,
    feedback: Optional[str] = None,
) -> SpawnTask:
    """Reject a proposal.

    With feedback: regenerate the prompt and return to ``awaiting_approval``
    (unless the iteration cap is hit, in which case the task fails). Without
    feedback: terminal ``REJECTED``.
    """
    task = tasks_repo.get(task_id)
    if task is None:
        raise NotApprovable(f"no such task: {task_id}")
    if task.status != State.AWAITING_APPROVAL:
        raise NotApprovable(
            f"task {task_id} is {task.status.value}, not awaiting_approval"
        )

    if not feedback or not feedback.strip():
        tasks_repo.transition(task_id, State.REJECTED)
        emit_event(kind="task_rejected", event={"task_id": task_id})
        return tasks_repo.get(task_id)  # type: ignore[return-value]

    # Cap check: approval_iterations counts prior reject-with-feedback rounds.
    if task.approval_iterations + 1 >= config.max_revision_iterations:
        tasks_repo.set_error(
            task_id, f"exceeded {config.max_revision_iterations} revision rounds"
        )
        tasks_repo.transition(task_id, State.FAILED)
        emit_event(
            kind="task_failed",
            event={"task_id": task_id, "error": "revision cap exceeded"},
        )
        return tasks_repo.get(task_id)  # type: ignore[return-value]

    # Record feedback + bump iteration count, roll back to WRITING_PROMPT.
    tasks_repo.set_revision_feedback(task_id, feedback)
    tasks_repo.transition(task_id, State.WRITING_PROMPT)
    emit_event(
        kind="task_transition",
        event={"task_id": task_id, "status": State.WRITING_PROMPT.value},
    )

    task = tasks_repo.get(task_id)  # refreshed
    assert task is not None and task.proposed_manifest is not None
    manifest = task.proposed_manifest

    # Regenerate ONLY the prompt — research + spec are cached on the task.
    report = reports_repo.get(task.research_report_id) if task.research_report_id else None
    if report is None:
        raise NotApprovable("cannot revise: research report missing")

    new_prompt = generate_system_prompt(
        llm=llm,
        name=manifest.name,
        role=task.role_description,
        report=report.report,
        special_requirements=task.special_requirements,
        prior_prompt=manifest.system_prompt,
        revision_feedback=feedback,
        config=config,
    )
    manifest.system_prompt = new_prompt
    tasks_repo.set_manifest(task_id, manifest)

    final = tasks_repo.transition(task_id, State.AWAITING_APPROVAL)
    emit_event(
        kind="awaiting_approval",
        event={"task_id": task_id, "slug": manifest.slug, "name": manifest.name},
    )
    return final
