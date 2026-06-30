"""Persistence repositories for the three tables.

All DB access goes through these classes. The spawn-task repo is the single
place state transitions are validated (:func:`agent_factory.models.assert_transition`),
so an illegal transition fails loudly no matter who attempts it.
"""

from __future__ import annotations

import datetime as _dt
import json
import sqlite3
import uuid
from typing import Optional

from agent_factory.models import (
    ProposedManifest,
    ResearchReport,
    SkillsReport,
    SpawnedAgent,
    SpawnTask,
    State,
    assert_transition,
)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex


# --------------------------------------------------------------------------- #
# research_reports
# --------------------------------------------------------------------------- #


class ResearchReportRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, *, query: str, normalized: str, report: SkillsReport) -> ResearchReport:
        rid = _new_id()
        created = _now()
        self._conn.execute(
            "INSERT INTO research_reports (id, query, normalized_query, report_json, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (rid, query, normalized, report.model_dump_json(), created),
        )
        self._conn.commit()
        return ResearchReport(
            id=rid, query=query, normalized_query=normalized, report=report, created_at=created
        )

    def get(self, report_id: str) -> Optional[ResearchReport]:
        row = self._conn.execute(
            "SELECT * FROM research_reports WHERE id = ?", (report_id,)
        ).fetchone()
        return self._row_to_model(row) if row else None

    def get_fresh(self, normalized: str, *, ttl_hours: int) -> Optional[ResearchReport]:
        cutoff = (
            _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=ttl_hours)
        ).isoformat()
        row = self._conn.execute(
            "SELECT * FROM research_reports WHERE normalized_query = ? AND created_at >= ?"
            " ORDER BY created_at DESC LIMIT 1",
            (normalized, cutoff),
        ).fetchone()
        return self._row_to_model(row) if row else None

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> ResearchReport:
        return ResearchReport(
            id=row["id"],
            query=row["query"],
            normalized_query=row["normalized_query"],
            report=SkillsReport.model_validate_json(row["report_json"]),
            created_at=row["created_at"],
        )


# --------------------------------------------------------------------------- #
# spawn_tasks
# --------------------------------------------------------------------------- #


class SpawnTaskRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def create(
        self,
        *,
        requested_by: str,
        name_hint: str,
        role_description: str,
        special_requirements: Optional[str] = None,
    ) -> SpawnTask:
        tid = _new_id()
        created = _now()
        self._conn.execute(
            "INSERT INTO spawn_tasks (id, requested_by, name_hint, role_description,"
            " special_requirements, status, approval_iterations, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, 0, ?)",
            (
                tid,
                requested_by,
                name_hint,
                role_description,
                special_requirements,
                State.PENDING.value,
                created,
            ),
        )
        self._conn.commit()
        return self.get(tid)  # type: ignore[return-value]

    def get(self, task_id: str) -> Optional[SpawnTask]:
        row = self._conn.execute(
            "SELECT * FROM spawn_tasks WHERE id = ?", (task_id,)
        ).fetchone()
        return self._row_to_model(row) if row else None

    def list_by_status(self, status: State) -> list[SpawnTask]:
        rows = self._conn.execute(
            "SELECT * FROM spawn_tasks WHERE status = ? ORDER BY created_at DESC",
            (status.value,),
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def list_all(self) -> list[SpawnTask]:
        rows = self._conn.execute(
            "SELECT * FROM spawn_tasks ORDER BY created_at DESC"
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def count_today(self, requested_by: str) -> int:
        start = _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
        row = self._conn.execute(
            "SELECT COUNT(*) AS n FROM spawn_tasks WHERE requested_by = ? AND created_at >= ?",
            (requested_by, start),
        ).fetchone()
        return int(row["n"])

    def transition(self, task_id: str, dst: State) -> SpawnTask:
        task = self.get(task_id)
        if task is None:
            raise ValueError(f"no such task: {task_id}")
        assert_transition(task.status, dst)
        self._conn.execute(
            "UPDATE spawn_tasks SET status = ? WHERE id = ?", (dst.value, task_id)
        )
        self._conn.commit()
        return self.get(task_id)  # type: ignore[return-value]

    def set_research_report(self, task_id: str, report_id: str) -> None:
        self._conn.execute(
            "UPDATE spawn_tasks SET research_report_id = ? WHERE id = ?",
            (report_id, task_id),
        )
        self._conn.commit()

    def set_manifest(self, task_id: str, manifest: ProposedManifest) -> None:
        self._conn.execute(
            "UPDATE spawn_tasks SET proposed_manifest = ? WHERE id = ?",
            (manifest.model_dump_json(), task_id),
        )
        self._conn.commit()

    def set_error(self, task_id: str, error: str) -> None:
        self._conn.execute(
            "UPDATE spawn_tasks SET error = ? WHERE id = ?", (error[:2000], task_id)
        )
        self._conn.commit()

    def set_revision_feedback(self, task_id: str, feedback: str) -> None:
        self._conn.execute(
            "UPDATE spawn_tasks SET revision_feedback = ?,"
            " approval_iterations = approval_iterations + 1 WHERE id = ?",
            (feedback, task_id),
        )
        self._conn.commit()

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> SpawnTask:
        manifest = row["proposed_manifest"]
        return SpawnTask(
            id=row["id"],
            requested_by=row["requested_by"],
            name_hint=row["name_hint"],
            role_description=row["role_description"],
            special_requirements=row["special_requirements"],
            status=State(row["status"]),
            research_report_id=row["research_report_id"],
            proposed_manifest=(
                ProposedManifest.model_validate_json(manifest) if manifest else None
            ),
            approval_iterations=row["approval_iterations"],
            revision_feedback=row["revision_feedback"],
            error=row["error"],
            created_at=row["created_at"],
        )


# --------------------------------------------------------------------------- #
# spawned_agents
# --------------------------------------------------------------------------- #


class SpawnedAgentRepo:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def save(self, agent: SpawnedAgent) -> SpawnedAgent:
        self._conn.execute(
            "INSERT INTO spawned_agents (id, slug, name, specialty, system_prompt,"
            " tool_allowlist, model, status, created_by_task_id, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                agent.id,
                agent.slug,
                agent.name,
                agent.specialty,
                agent.system_prompt,
                json.dumps(agent.tool_allowlist),
                agent.model,
                agent.status,
                agent.created_by_task_id,
                agent.created_at or _now(),
            ),
        )
        self._conn.commit()
        return self.get_by_slug(agent.slug)  # type: ignore[return-value]

    def get_by_slug(self, slug: str) -> Optional[SpawnedAgent]:
        row = self._conn.execute(
            "SELECT * FROM spawned_agents WHERE slug = ?", (slug,)
        ).fetchone()
        return self._row_to_model(row) if row else None

    def slug_exists(self, slug: str) -> bool:
        row = self._conn.execute(
            "SELECT 1 FROM spawned_agents WHERE slug = ?", (slug,)
        ).fetchone()
        return row is not None

    def list_active(self) -> list[SpawnedAgent]:
        rows = self._conn.execute(
            "SELECT * FROM spawned_agents WHERE status = 'active' ORDER BY created_at"
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def list_all(self) -> list[SpawnedAgent]:
        rows = self._conn.execute(
            "SELECT * FROM spawned_agents ORDER BY created_at"
        ).fetchall()
        return [self._row_to_model(r) for r in rows]

    def archive(self, slug: str) -> None:
        self._conn.execute(
            "UPDATE spawned_agents SET status = 'archived' WHERE slug = ?", (slug,)
        )
        self._conn.commit()

    @staticmethod
    def _row_to_model(row: sqlite3.Row) -> SpawnedAgent:
        return SpawnedAgent(
            id=row["id"],
            slug=row["slug"],
            name=row["name"],
            specialty=row["specialty"],
            system_prompt=row["system_prompt"],
            tool_allowlist=json.loads(row["tool_allowlist"]),
            model=row["model"],
            status=row["status"],
            created_by_task_id=row["created_by_task_id"],
            created_at=row["created_at"],
        )


def new_agent_id() -> str:
    return _new_id()


def now_iso() -> str:
    return _now()
