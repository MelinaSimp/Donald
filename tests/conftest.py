from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_factory.config import Config  # noqa: E402
from agent_factory.db import init_db  # noqa: E402
from agent_factory.events import LoggingEventSink  # noqa: E402
from agent_factory.llm import FakeLLMClient  # noqa: E402
from agent_factory.repos import (  # noqa: E402
    ResearchReportRepo,
    SpawnedAgentRepo,
    SpawnTaskRepo,
)
from agent_factory.search import StaticSearchBackend  # noqa: E402
from agent_factory.tools.builtins import build_default_registry  # noqa: E402
from tests.helpers import make_responder  # noqa: E402


@pytest.fixture()
def config(tmp_path: Path) -> Config:
    return Config(db_path=tmp_path / "factory.db", specs_dir=tmp_path / "agent-specs")


@pytest.fixture()
def conn(config: Config):
    c = init_db(config.db_path)
    yield c
    c.close()


@pytest.fixture()
def repos(conn):
    return {
        "tasks": SpawnTaskRepo(conn),
        "reports": ResearchReportRepo(conn),
        "agents": SpawnedAgentRepo(conn),
    }


@pytest.fixture()
def llm() -> FakeLLMClient:
    return FakeLLMClient(make_responder())


@pytest.fixture()
def search() -> StaticSearchBackend:
    return StaticSearchBackend(
        default=[{"url": "https://example.com", "title": "doc", "content": "snippet"}]
    )


@pytest.fixture()
def registry(search):
    return build_default_registry(search)


@pytest.fixture()
def events() -> LoggingEventSink:
    return LoggingEventSink(verbose=False)
