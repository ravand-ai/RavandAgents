"""File memory store isolation (GitHub issue #95).

Source of law: docs/SECURITY.md isolation table and docs/MODULAR.md Memory.
Scope in every key. No cross-scope merge. No tokens in files.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ravand_memory import FailClosed, FileStore

FORBIDDEN = ("sk-", "xai-", "Bearer", "cookies")


def _files_under(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()]


def test_write_read_same_scope(tmp_path: Path) -> None:
    store = FileStore(tmp_path, isolation="project", scope_key="acme")
    store.write("ship isolation first")
    notes = store.read()
    assert "ship isolation first" in notes


def test_deny_other_profile(tmp_path: Path) -> None:
    work = FileStore(tmp_path, isolation="profile", scope_key="work")
    work.write("work-only note")
    personal = FileStore(tmp_path, isolation="profile", scope_key="personal")
    notes = personal.read()
    assert "work-only note" not in notes
    assert list(notes) == []


def test_no_cross_scope_merge(tmp_path: Path) -> None:
    session = FileStore(tmp_path, isolation="session", scope_key="run-1")
    session.write("session scratch")
    project = FileStore(tmp_path, isolation="project", scope_key="run-1")
    notes = project.read()
    assert "session scratch" not in notes
    assert list(notes) == []


def test_dot_scope_key_fails_closed(tmp_path: Path) -> None:
    with pytest.raises(FailClosed):
        FileStore(tmp_path, isolation="session", scope_key="..")
    with pytest.raises(FailClosed):
        FileStore(tmp_path, isolation="project", scope_key=".")


def test_no_sk_in_files(tmp_path: Path) -> None:
    store = FileStore(tmp_path, isolation="session", scope_key="s1")
    store.write("clean note")
    with pytest.raises(FailClosed):
        store.write("token sk-secret-value must not persist")
    with pytest.raises(FailClosed):
        store.write("see ~/.grok/cookies")
    assert "clean note" in store.read()
    for path in _files_under(tmp_path):
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN:
            assert marker not in text, f"{path} leaked {marker!r}"
        assert "sk-" not in text
