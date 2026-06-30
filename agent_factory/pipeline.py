"""Tier 3 — the spawn pipeline (the state machine itself).

Wires Tiers 1 and 2 into a single call, :meth:`SpawnPipeline.run`, that walks
a ``spawn_tasks`` row from ``pending`` to ``awaiting_approval``:

1. load the task
2. pick + validate the slug (refuse reserved/colliding slugs *before* any LLM
   work, so a clean error costs zero tokens)
3. RESEARCHING -> run Tier 1, persist the report id
4. DRAFTING_SPEC -> write the spec markdown
5. WRITING_PROMPT -> generate the system prompt
6. build the proposed manifest, save it on the task
7. AWAITING_APPROVAL -> emit so the approval surface knows there's work

The whole method is wrapped so *any* exception lands the task in ``FAILED``
with the error recorded — once a spawn task starts, it ends in a terminal
state. The CLI invokes this synchronously and awaits completion, which
sidesteps the asyncio fire-and-forget GC hazard entirely.
"""

from __future__ import annotations

from typing import Optional

from agent_factory.config import Config
from agent_factory.events import EventSink
from agent_factory.llm import LLMClient
from agent_factory.models import ProposedManifest, SpawnTask, State, slugify
from agent_factory.repos import ResearchReportRepo, SpawnedAgentRepo, SpawnTaskRepo
from agent_factory.research import run_research
from agent_factory.sanitize import InjectionRefused, assert_clean
from agent_factory.search import SearchBackend
from agent_factory.spec import generate_system_prompt, write_spec_markdown
from agent_factory.tools.registry import ToolRegistry


class SlugCollision(Exception):
    pass


class DailyCapExceeded(Exception):
    pass


class SpawnPipeline:
    def __init__(
        self,
        *,
        config: Config,
        llm: LLMClient,
        tasks_repo: SpawnTaskRepo,
        reports_repo: ResearchReportRepo,
        agents_repo: SpawnedAgentRepo,
        tool_registry: ToolRegistry,
        search_backend: SearchBackend,
        emit_event: EventSink,
    ) -> None:
        self.cfg = config
        self.llm = llm
        self.tasks = tasks_repo
        self.reports = reports_repo
        self.agents = agents_repo
        self.tools = tool_registry
        self.search = search_backend
        self.emit = emit_event

    # --- helpers ----------------------------------------------------------- #

    def pick_slug(self, name_hint: str) -> str:
        slug = slugify(name_hint)
        if slug in self.cfg.reserved_slugs:
            raise SlugCollision(f"slug '{slug}' is reserved")
        if self.agents.slug_exists(slug):
            raise SlugCollision(f"slug '{slug}' is already taken by an existing agent")
        return slug

    def _to(self, task_id: str, dst: State) -> SpawnTask:
        task = self.tasks.transition(task_id, dst)
        self.emit(kind="task_transition", event={"task_id": task_id, "status": dst.value})
        return task

    # --- entry point ------------------------------------------------------- #

    def run(self, task_id: str) -> SpawnTask:
        """Walk the task to a terminal state. Never raises past here."""
        task = self.tasks.get(task_id)
        if task is None:
            raise ValueError(f"no such task: {task_id}")
        if task.status != State.PENDING:
            raise ValueError(
                f"task {task_id} is in state {task.status.value}, expected pending"
            )

        try:
            # Refuse injection and reserved/colliding slugs before any LLM call.
            assert_clean(task.role_description, field="role_description")
            assert_clean(task.special_requirements or "", field="special_requirements")
            slug = self.pick_slug(task.name_hint)

            # 1. Research
            self._to(task_id, State.RESEARCHING)
            report = run_research(
                task.role_description,
                llm=self.llm,
                reports_repo=self.reports,
                config=self.cfg,
                search_backend=self.search,
                tool_catalog=self.tools.factory_allowed_names(),
            )
            self.tasks.set_research_report(task_id, report.id)

            # Intersect requested tools with what we actually allow handing out.
            allowed = set(self.tools.factory_allowed_names())
            tool_allowlist = [t for t in report.report.tools_available if t in allowed]

            # 2. Spec markdown
            self._to(task_id, State.DRAFTING_SPEC)
            write_spec_markdown(
                slug=slug,
                name=task.name_hint,
                role=task.role_description,
                special_requirements=task.special_requirements,
                report=report.report,
                tool_allowlist=tool_allowlist,
                model=self.cfg.agent_model,
                config=self.cfg,
            )

            # 3. System prompt
            self._to(task_id, State.WRITING_PROMPT)
            system_prompt = generate_system_prompt(
                llm=self.llm,
                name=task.name_hint,
                role=task.role_description,
                report=report.report,
                special_requirements=task.special_requirements,
                config=self.cfg,
            )

            # 4. Manifest
            manifest = ProposedManifest(
                slug=slug,
                name=task.name_hint,
                specialty=report.report.domain,
                system_prompt=system_prompt,
                tool_allowlist=tool_allowlist,
                model=self.cfg.agent_model,
            )
            self.tasks.set_manifest(task_id, manifest)

            # 5. Await approval
            final = self._to(task_id, State.AWAITING_APPROVAL)
            self.emit(
                kind="awaiting_approval",
                event={
                    "task_id": task_id,
                    "slug": slug,
                    "name": manifest.name,
                    "tool_allowlist": tool_allowlist,
                    "tools_wishlist": [w.model_dump() for w in report.report.tools_wishlist],
                },
            )
            return final

        except Exception as exc:  # noqa: BLE001 - must land in a terminal state
            self.tasks.set_error(task_id, str(exc))
            # transition is valid from any non-terminal state to FAILED
            try:
                current = self.tasks.get(task_id)
                if current and current.status not in (
                    State.APPROVED,
                    State.REJECTED,
                    State.FAILED,
                ):
                    self.tasks.transition(task_id, State.FAILED)
                    self.emit(
                        kind="task_failed",
                        event={"task_id": task_id, "error": str(exc)},
                    )
            except Exception:  # pragma: no cover - defensive
                pass
            return self.tasks.get(task_id)  # type: ignore[return-value]


def create_spawn_task(
    *,
    tasks_repo: SpawnTaskRepo,
    config: Config,
    requested_by: str,
    name_hint: str,
    role_description: str,
    special_requirements: Optional[str] = None,
) -> SpawnTask:
    """Create a spawn task, enforcing the daily cap and injection refusal.

    The cap is enforced here (at creation) rather than at approval so an
    attacker cannot queue thousands of tasks even if approvals are gated.
    """
    # Refuse obviously hostile input up front.
    assert_clean(role_description, field="role_description")
    assert_clean(special_requirements or "", field="special_requirements")

    used = tasks_repo.count_today(requested_by)
    if used >= config.daily_cap:
        raise DailyCapExceeded(
            f"daily cap of {config.daily_cap} spawn tasks reached for {requested_by}"
        )
    return tasks_repo.create(
        requested_by=requested_by,
        name_hint=name_hint,
        role_description=role_description,
        special_requirements=special_requirements,
    )
