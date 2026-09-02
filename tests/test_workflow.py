"""Workflow graph: Policy then dispatch (GitHub issue #139).

Source of law: docs/HLD.md Workflow, docs/MODULAR.md Workflow,
docs/SCHEMA.md [workflow].
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ravand_audit import AuditLog
from ravand_bus import Bus
from ravand_policy import PolicyDenied
from ravand_runtime.workflow import load_workflow, run_workflow
from ravand_sessions import SessionStore

QUEUE_TASKS = "q.tasks"
FORBIDDEN = ("sk-", "xai-", "Bearer", "cookies")


def _write_harness(
    repo: Path,
    *,
    profile: str = "work",
    default: str = "grok",
    deny: str = "[]",
    classification: str = "internal",
    extra: str = "",
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "harness.toml").write_text(
        "\n".join(
            [
                f'profile = "{profile}"',
                f'default = "{default}"',
                'overflow = "kimi"',
                f"deny = {deny}",
                'permissions = "repo-only"',
                f'classification = "{classification}"',
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


def _audit_events(root: Path) -> list[dict[str, object]]:
    path = root / "audit.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _workflow_extra(*, steps: str, workflow_id: str | None = "ship") -> str:
    lines = ["[workflow]"]
    if workflow_id is not None:
        lines.append(f'id = "{workflow_id}"')
    lines.append(f"steps = [{steps}]")
    return "\n".join(lines) + "\n"


def test_load_workflow_from_harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=_workflow_extra(
            steps=(
                '{ id = "lint", prompt = "run linter" }, '
                '{ id = "review", prompt = "review the diff", '
                'needs = ["lint"], agent = "kimi" }'
            )
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    workflow = load_workflow(repo)
    assert workflow is not None
    assert workflow.id == "ship"
    assert [step.id for step in workflow.steps] == ["lint", "review"]
    assert workflow.steps[0].prompt == "run linter"
    assert workflow.steps[1].needs == ("lint",)
    assert workflow.steps[1].agent == "kimi"


def test_missing_workflow_section_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    assert load_workflow(repo) is None
    assert run_workflow(repo) == []


def test_run_steps_in_topo_order_dispatches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=_workflow_extra(
            steps=(
                '{ id = "review", prompt = "review the diff", '
                'depends = ["lint"], agent = "kimi" }, '
                '{ id = "lint", prompt = "run linter" }'
            )
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    ran = run_workflow(
        repo,
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
    assert first.prompt == "run linter"
    assert first.agent == "grok"
    assert second.task_id.startswith("ship:review:")
    assert second.prompt == "review the diff"
    assert second.agent == "kimi"
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert len(list((home / "sessions").glob("*.json"))) == 2


def test_injected_run_uses_topo_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=_workflow_extra(
            steps=(
                '{ id = "review", prompt = "review the diff", '
                'needs = ["lint"] }, '
                '{ id = "lint", prompt = "run linter" }'
            )
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    seen: list[str] = []

    def _run(step: object) -> None:
        seen.append(getattr(step, "id"))

    ran = run_workflow(repo, bus=bus, run=_run, audit=AuditLog(home))
    assert [step.id for step in ran] == ["lint", "review"]
    assert seen == ["lint", "review"]
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert list((home / "sessions").glob("*.json")) == []


def test_cycle_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=_workflow_extra(
            steps=(
                '{ id = "a", prompt = "first", needs = ["b"] }, '
                '{ id = "b", prompt = "second", needs = ["a"] }'
            )
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    with pytest.raises(PolicyDenied):
        load_workflow(repo)
    with pytest.raises(PolicyDenied):
        run_workflow(
            repo,
            bus=bus,
            store=store,
            audit=AuditLog(home),
        )
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert list((home / "sessions").glob("*.json")) == []


def test_unknown_step_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=_workflow_extra(
            steps='{ id = "review", prompt = "review", needs = ["missing"] }'
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    with pytest.raises(PolicyDenied):
        load_workflow(repo)
    with pytest.raises(PolicyDenied):
        run_workflow(
            repo,
            bus=bus,
            store=store,
            audit=AuditLog(home),
        )
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert list((home / "sessions").glob("*.json")) == []


def test_denied_agent_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        deny='["kimi"]',
        extra=_workflow_extra(
            steps=(
                '{ id = "lint", prompt = "run linter" }, '
                '{ id = "review", prompt = "review the diff", '
                'needs = ["lint"], agent = "kimi" }'
            )
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    with pytest.raises(PolicyDenied):
        run_workflow(
            repo,
            bus=bus,
            store=store,
            audit=AuditLog(home),
        )
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert list((home / "sessions").glob("*.json")) == []
    events = _audit_events(home)
    assert "agent.denied" in [event["type"] for event in events]
    blob = (home / "audit.jsonl").read_text(encoding="utf-8")
    for marker in FORBIDDEN:
        assert marker not in blob


def test_raw_key_in_graph_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=_workflow_extra(
            steps=(
                '{ id = "lint", prompt = "run linter", '
                'key = "sk-secret-value" }'
            )
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with pytest.raises(PolicyDenied):
        load_workflow(repo)
    bus = Bus()
    store = SessionStore(home)
    with pytest.raises(PolicyDenied):
        run_workflow(
            repo,
            bus=bus,
            store=store,
            audit=AuditLog(home),
        )
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    text = (repo / "harness.toml").read_text(encoding="utf-8")
    assert "sk-secret-value" in text


def test_unknown_function_binding_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    extra = (
        '[functions]\nallow = ["jira.comment"]\n'
        + _workflow_extra(
            steps=(
                '{ id = "lint", prompt = "run linter", '
                'functions = ["unknown-fn"] }'
            )
        )
    )
    _write_harness(repo, extra=extra)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    with pytest.raises(PolicyDenied):
        run_workflow(
            repo,
            bus=bus,
            store=store,
            audit=AuditLog(home),
        )
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert list((home / "sessions").glob("*.json")) == []
