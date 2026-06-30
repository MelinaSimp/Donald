"""Shared fixtures: isolate HOME (memory/config) and CWD (file tools) per test."""

import importlib

import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Point ~/.donald at a throwaway dir so tests never touch the real home."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # Reload modules that bind paths at import time off the patched HOME.
    import donald.memory as memory

    importlib.reload(memory)
    return tmp_path


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """Run inside a throwaway working directory for the file tools."""
    monkeypatch.chdir(tmp_path)
    return tmp_path
