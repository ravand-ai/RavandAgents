"""Shared Policy-step runner (GitHub issue #176).

Workflow stays a graph; pipeline stays an ordered list.
Both call the same Policy resolve + unique task_id dispatch helper.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from ravand_audit import AuditLog
from ravand_bus import Bus
from ravand_policy import PolicyDenied
from ravand_runtime.step_runner import run_policy_steps
from ravand_sessions import SessionStore

QUEUE_TASKS = "q.tasks"


@dataclass(frozen=True)
class _Step:
    id: str
    prompt: str
    agent: str | None = None
    account: str | None = None
    functions: tuple[str, ...] = ()
    tools: tuple[str, ...] = ()
    subagents: tuple[str, ...] = ()


def _write_harness(
    repo: Path,
    *,
    deny: str = "[]",
    extra: str = "",
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "harness.toml").write_text(
        "\n".join(
            [
                'profile = "work"',
                'default = "grok"',
                'overflow = "kimi"',
                f"deny = {deny}",
                'permissions = "repo-only"',
                'classification = "internal"',
                extra,
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


def test_run_policy_steps_dispatches_unique_task_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    steps = (
        _Step(id="lint", prompt="run linter"),
        _Step(id="review", prompt="review the diff", agent="kimi"),
    )
    ran = run_policy_steps(
        steps,
        cwd=repo,
        root_id="ship",
        kind="workflow",
        bus=bus,
        store=store,
        audit=AuditLog(home),
    )
    assert [step.id for step in ran] == ["lint", "review"]
    first = bus.read(QUEUE_TASKS, visibility_timeout=600)
    second = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert first is not None
    assert second is not None
    assert first.task_id.startswith("ship:lint:")
    assert second.task_id.startswith("ship:review:")
    assert first.task_id != second.task_id
    assert first.agent == "grok"
    assert second.agent == "kimi"


def test_run_policy_steps_denied_agent_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(repo, deny='["kimi"]')
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    with pytest.raises(PolicyDenied):
        run_policy_steps(
            (_Step(id="review", prompt="review", agent="kimi"),),
            cwd=repo,
            root_id="ship",
            kind="pipeline",
            bus=bus,
            store=store,
            audit=AuditLog(home),
        )
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert list((home / "sessions").glob("*.json")) == []
