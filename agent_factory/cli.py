"""Command-line approval surface for the Factory.

Commands map onto every verification step in the build plan:

    factory init-db
    factory research "<domain>"
    factory spawn --name <name> --role "<desc>" [--requirements "..."] [--by user]
    factory run-pipeline <task_id>
    factory show-task <task_id>
    factory list-tasks
    factory pending                       # hydration: awaiting_approval + manifests
    factory approve <task_id>
    factory reject <task_id> [--feedback "..."]
    factory list-agents
    factory dispatch <slug> "<message>"
    factory generate-prompt --report <skills_report.json> --name <n> --role "<r>"

The pipeline runs synchronously to completion, so there is no fire-and-forget
task that could be garbage-collected mid-run.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from agent_factory.config import Config
from agent_factory.db import init_db
from agent_factory.events import LoggingEventSink
from agent_factory.llm import AnthropicLLMClient, LLMClient
from agent_factory.models import SkillsReport
from agent_factory.approval import get_pending, handle_approve, handle_reject
from agent_factory.pipeline import SpawnPipeline, create_spawn_task
from agent_factory.repos import ResearchReportRepo, SpawnedAgentRepo, SpawnTaskRepo
from agent_factory.research import run_research
from agent_factory.runtime import ConfigDrivenAgent, RegistryWatcher
from agent_factory.search import NullSearchBackend
from agent_factory.spec import generate_system_prompt
from agent_factory.tools.builtins import build_default_registry


class _Ctx:
    """Lazily-constructed wiring shared by all commands."""

    def __init__(self, config: Config) -> None:
        self.cfg = config
        self.conn = init_db(config.db_path)
        self.tasks = SpawnTaskRepo(self.conn)
        self.reports = ResearchReportRepo(self.conn)
        self.agents = SpawnedAgentRepo(self.conn)
        self.search = NullSearchBackend()
        self.registry = build_default_registry(self.search)
        self.events = LoggingEventSink()
        self._llm: Optional[LLMClient] = None
        self._watcher: Optional[RegistryWatcher] = None

    @property
    def llm(self) -> LLMClient:
        if self._llm is None:
            try:
                self._llm = AnthropicLLMClient()
            except Exception as exc:  # noqa: BLE001
                raise SystemExit(
                    "An Anthropic client is required for this command. Set "
                    f"ANTHROPIC_API_KEY. ({exc})"
                )
        return self._llm

    @property
    def watcher(self) -> RegistryWatcher:
        if self._watcher is None:
            self._watcher = RegistryWatcher(
                agents_repo=self.agents,
                tool_registry=self.registry,
                llm=self.llm,
                config=self.cfg,
            )
            self._watcher.refresh()  # load existing approved agents
        return self._watcher

    def pipeline(self) -> SpawnPipeline:
        return SpawnPipeline(
            config=self.cfg,
            llm=self.llm,
            tasks_repo=self.tasks,
            reports_repo=self.reports,
            agents_repo=self.agents,
            tool_registry=self.registry,
            search_backend=self.search,
            emit_event=self.events,
        )


# --------------------------------------------------------------------------- #
# command handlers
# --------------------------------------------------------------------------- #


def cmd_init_db(ctx: _Ctx, args: argparse.Namespace) -> int:
    print(f"Database ready at {ctx.cfg.db_path}")
    print(f"Specs dir: {ctx.cfg.specs_dir}")
    return 0


def cmd_research(ctx: _Ctx, args: argparse.Namespace) -> int:
    report = run_research(
        args.domain,
        llm=ctx.llm,
        reports_repo=ctx.reports,
        config=ctx.cfg,
        search_backend=ctx.search,
        tool_catalog=ctx.registry.factory_allowed_names(),
    )
    print(json.dumps(report.model_dump(), indent=2))
    return 0


def cmd_spawn(ctx: _Ctx, args: argparse.Namespace) -> int:
    task = create_spawn_task(
        tasks_repo=ctx.tasks,
        config=ctx.cfg,
        requested_by=args.by,
        name_hint=args.name,
        role_description=args.role,
        special_requirements=args.requirements,
    )
    print(f"Created spawn task {task.id} (status={task.status.value})")
    return 0


def cmd_run_pipeline(ctx: _Ctx, args: argparse.Namespace) -> int:
    task = ctx.pipeline().run(args.task_id)
    print(f"Task {task.id} -> {task.status.value}")
    if task.error:
        print(f"error: {task.error}")
    return 0 if task.status.value == "awaiting_approval" else 1


def cmd_show_task(ctx: _Ctx, args: argparse.Namespace) -> int:
    task = ctx.tasks.get(args.task_id)
    if task is None:
        print("no such task", file=sys.stderr)
        return 1
    print(json.dumps(task.model_dump(), indent=2, default=str))
    return 0


def cmd_list_tasks(ctx: _Ctx, args: argparse.Namespace) -> int:
    for task in ctx.tasks.list_all():
        print(f"{task.id}  {task.status.value:<18}  {task.name_hint}")
    return 0


def cmd_pending(ctx: _Ctx, args: argparse.Namespace) -> int:
    print(json.dumps(get_pending(ctx.tasks), indent=2, default=str))
    return 0


def cmd_approve(ctx: _Ctx, args: argparse.Namespace) -> int:
    agent = handle_approve(
        task_id=args.task_id,
        tasks_repo=ctx.tasks,
        agents_repo=ctx.agents,
        emit_event=ctx.events,
        notify_registry=ctx.watcher.notify,
    )
    print(f"Approved. Agent '{agent.slug}' is now active and dispatchable.")
    return 0


def cmd_reject(ctx: _Ctx, args: argparse.Namespace) -> int:
    # Only needs the LLM when feedback triggers a regeneration.
    llm = ctx.llm if args.feedback else None
    task = handle_reject(
        task_id=args.task_id,
        tasks_repo=ctx.tasks,
        reports_repo=ctx.reports,
        config=ctx.cfg,
        llm=llm,  # type: ignore[arg-type]
        emit_event=ctx.events,
        feedback=args.feedback,
    )
    print(f"Task {task.id} -> {task.status.value} (iterations={task.approval_iterations})")
    return 0


def cmd_list_agents(ctx: _Ctx, args: argparse.Namespace) -> int:
    for a in ctx.agents.list_all():
        print(f"{a.slug:<24} {a.status:<10} {a.model:<22} tools={a.tool_allowlist}")
    return 0


def cmd_dispatch(ctx: _Ctx, args: argparse.Namespace) -> int:
    row = ctx.agents.get_by_slug(args.slug)
    if row is None or row.status != "active":
        print(f"no active agent '{args.slug}'", file=sys.stderr)
        return 1
    agent = ConfigDrivenAgent(row, ctx.registry, ctx.llm, max_iters=ctx.cfg.agent_max_iters)
    print(agent.run(args.message))
    return 0


def cmd_generate_prompt(ctx: _Ctx, args: argparse.Namespace) -> int:
    report = SkillsReport.model_validate_json(Path(args.report).read_text())
    prompt = generate_system_prompt(
        llm=ctx.llm,
        name=args.name,
        role=args.role,
        report=report,
        special_requirements=args.requirements,
        config=ctx.cfg,
    )
    print(prompt)
    return 0


# --------------------------------------------------------------------------- #
# arg parsing
# --------------------------------------------------------------------------- #


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="factory", description="Agent Factory CLI")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("init-db", help="create/migrate the database").set_defaults(func=cmd_init_db)

    sp = sub.add_parser("research", help="run the research subagent for a domain")
    sp.add_argument("domain")
    sp.set_defaults(func=cmd_research)

    sp = sub.add_parser("spawn", help="create a spawn task")
    sp.add_argument("--name", required=True)
    sp.add_argument("--role", required=True)
    sp.add_argument("--requirements", default=None)
    sp.add_argument("--by", default="cli-user")
    sp.set_defaults(func=cmd_spawn)

    sp = sub.add_parser("run-pipeline", help="run a spawn task to awaiting_approval")
    sp.add_argument("task_id")
    sp.set_defaults(func=cmd_run_pipeline)

    sp = sub.add_parser("show-task", help="print a task as JSON")
    sp.add_argument("task_id")
    sp.set_defaults(func=cmd_show_task)

    sub.add_parser("list-tasks", help="list all spawn tasks").set_defaults(func=cmd_list_tasks)
    sub.add_parser("pending", help="list awaiting_approval tasks + manifests").set_defaults(
        func=cmd_pending
    )

    sp = sub.add_parser("approve", help="approve a proposed agent")
    sp.add_argument("task_id")
    sp.set_defaults(func=cmd_approve)

    sp = sub.add_parser("reject", help="reject (optionally with feedback to revise)")
    sp.add_argument("task_id")
    sp.add_argument("--feedback", default=None)
    sp.set_defaults(func=cmd_reject)

    sub.add_parser("list-agents", help="list spawned agents").set_defaults(func=cmd_list_agents)

    sp = sub.add_parser("dispatch", help="run a spawned agent on a message")
    sp.add_argument("slug")
    sp.add_argument("message")
    sp.set_defaults(func=cmd_dispatch)

    sp = sub.add_parser("generate-prompt", help="generate a system prompt from a Skills Report")
    sp.add_argument("--report", required=True)
    sp.add_argument("--name", required=True)
    sp.add_argument("--role", required=True)
    sp.add_argument("--requirements", default=None)
    sp.set_defaults(func=cmd_generate_prompt)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    ctx = _Ctx(Config.load())
    return args.func(ctx, args)


if __name__ == "__main__":
    raise SystemExit(main())
