"""Tests for Donald's long-term memory."""

import importlib

import donald.memory as memory


def _fresh():
    importlib.reload(memory)
    return memory


def test_starts_empty(home):
    m = _fresh()
    assert m.load() == ""
    assert m.block() == ""


def test_remember_appends(home):
    m = _fresh()
    m.remember("Operator goes by Adharsh.")
    m.remember("Prefers terse answers.")
    text = m.load()
    assert "Adharsh" in text and "terse" in text
    assert text.count("- ") == 2


def test_remember_ignores_blank(home):
    m = _fresh()
    out = m.remember("   ")
    assert "Nothing" in out
    assert not m.MEMORY_PATH.exists()


def test_block_strips_headers_and_wraps(home):
    m = _fresh()
    m.remember("Lives in Bengaluru.")
    block = m.block()
    assert "#" not in block  # the file header is stripped
    assert "Bengaluru" in block
    assert block.startswith("\n\nWhat you remember")


def test_replace_curates_and_backs_up(home):
    m = _fresh()
    m.remember("Lives in Bangalore.")
    m.remember("Lives in Bengaluru.")
    msg = m.replace("Lives in Bengaluru.")
    assert "1 item" in msg
    assert "Bangalore" not in m.load()
    assert m.BACKUP_PATH.exists()
    assert "Bangalore" in m.BACKUP_PATH.read_text()


def test_replace_empty_clears_body_keeps_file(home):
    m = _fresh()
    m.remember("Something.")
    m.replace("")
    assert m.MEMORY_PATH.exists()
    assert "Something" not in m.load()
    assert m.block() == ""


def test_clear_removes_file_and_backup(home):
    m = _fresh()
    m.remember("A.")
    m.replace("B.")  # creates a backup
    assert m.clear() is True
    assert not m.MEMORY_PATH.exists()
    assert not m.BACKUP_PATH.exists()
    assert m.clear() is False  # nothing left to remove
