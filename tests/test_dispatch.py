"""Dispatcher: policy resolve then Bus.send to q.tasks (GitHub issue #133)."""

from __future__ import annotations

from pathlib import Path

import pytest

from ravand_bus import Bus, FailClosed as BusFailClosed
from ravand_policy import PolicyDenied
from ravand_runtime.dispatch import dispatch
from ravand_sessions import FailClosed, SessionStore

QUEUE_TASKS = "q.tasks"


def _write_harness(
    repo: Path,
    *,
    profile: str = "work",
    default: str = "grok",
    overflow: str = "kimi",
    deny: str = "[]",
    classification: str = "internal",
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "harness.toml").write_text(
        "\n".join(
            [
                f'profile = "{profile}"',
                f'default = "{default}"',
                f'overflow = "{overflow}"',
                f"deny = {deny}",
                'permissions = "repo-only"',
                f'classification = "{classification}"',
                "",
                "[agents.grok]",
                'command = ["grok", "agent", "stdio"]',
                "",
                "[agents.kimi]",
                'command = ["kimi", "acp"]',
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_dispatch_sends_task_after_policy_resolve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    dispatch(
        repo,
        "ship the dispatcher",
        bus=bus,
        store=store,
        task_id="task-1",
    )
    got = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert got is not None
    assert got.task_id == "task-1"
    assert got.cwd_hint == str(repo.resolve())
    assert got.profile == "work"
    assert got.agent == "grok"
    assert got.prompt == "ship the dispatcher"
    assert got.permissions == "repo-only"
    assert got.overflow == "kimi"
    sessions = list((home / "sessions").glob("*.json"))
    assert len(sessions) == 1


def test_denied_policy_does_not_enqueue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_harness(repo, default="kimi", deny='["kimi"]')
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    with pytest.raises(PolicyDenied):
        dispatch(
            repo,
            "should not queue",
            bus=bus,
            store=store,
            task_id="task-deny",
        )
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert list((home / "sessions").glob("*.json")) == []


def test_session_store_rejects_second_start_when_running(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    store.start(
        task_id="task-1",
        cwd="/repo",
        profile="work",
        agent="grok",
        command=["grok", "agent", "stdio"],
    )
    with pytest.raises(FailClosed):
        store.start(
            task_id="task-1",
            cwd="/repo",
            profile="work",
            agent="grok",
            command=["grok", "agent", "stdio"],
        )


def test_session_store_rejects_second_start_when_done(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    record = store.start(
        task_id="task-2",
        cwd="/repo",
        profile="work",
        agent="grok",
        command=["grok", "agent", "stdio"],
    )
    store.finish(record.id, status="ok")
    with pytest.raises(FailClosed):
        store.start(
            task_id="task-2",
            cwd="/repo",
            profile="work",
            agent="grok",
            command=["grok", "agent", "stdio"],
        )


def test_session_store_allows_start_after_error(tmp_path: Path) -> None:
    store = SessionStore(tmp_path)
    record = store.start(
        task_id="task-3",
        cwd="/repo",
        profile="work",
        agent="grok",
        command=["grok", "agent", "stdio"],
    )
    store.finish(record.id, status="error")
    second = store.start(
        task_id="task-3",
        cwd="/repo",
        profile="work",
        agent="kimi",
        command=["kimi", "acp"],
    )
    assert second.status == "running"
    assert second.task_id == "task-3"


def test_dispatch_second_start_does_not_enqueue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    dispatch(repo, "first", bus=bus, store=store, task_id="task-1")
    with pytest.raises(FailClosed):
        dispatch(repo, "second", bus=bus, store=store, task_id="task-1")
    first = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert first is not None
    assert first.prompt == "first"
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None


def test_dispatch_secret_prompt_does_not_enqueue(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    with pytest.raises(BusFailClosed):
        dispatch(
            repo,
            "token sk-secret-value must not queue",
            bus=bus,
            store=store,
            task_id="task-secret",
        )
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert list((home / "sessions").glob("*.json")) == []
