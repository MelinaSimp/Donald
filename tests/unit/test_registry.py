"""Unit tests for conditional tool registration."""

from __future__ import annotations

from trillion.config import Settings
from trillion.tools.registry import ToolRegistry


def test_donald_tool_registered_when_url_set():
    settings = Settings(supabase_donald_url="postgresql://u:p@h:6543/postgres")
    registry = ToolRegistry.from_settings(settings)
    assert "query_donald" in registry
    assert registry.names() == ["query_donald"]


def test_no_tools_when_url_absent():
    registry = ToolRegistry.from_settings(Settings(supabase_donald_url=""))
    assert len(registry) == 0
    assert registry.names() == []


def test_settings_from_env_reads_uppercase_var():
    settings = Settings.from_env({"SUPABASE_DONALD_URL": "postgresql://x"})
    assert settings.supabase_donald_url == "postgresql://x"


def test_settings_from_env_defaults_empty():
    assert Settings.from_env({}).supabase_donald_url == ""
