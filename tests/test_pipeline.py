"""Pipeline ordered stages: Policy then dispatch (GitHub issue #140).

Source of law: docs/HLD.md Workflow and pipeline, docs/MODULAR.md Pipeline,
docs/SCHEMA.md [pipeline].
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

import pytest

from ravand_audit import AuditLog
from ravand_bus import Bus
from ravand_policy import PolicyDenied
from ravand_runtime.pipeline import load_pipeline, run_pipeline
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


def _pipeline_extra(*, stages: str, pipeline_id: str | None = "ship") -> str:
    lines = ["[pipeline]"]
    if pipeline_id is not None:
        lines.append(f'id = "{pipeline_id}"')
    lines.append(f"stages = [{stages}]")
    return "\n".join(lines) + "\n"


def test_load_pipeline_from_harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=_pipeline_extra(
            stages=(
                '{ id = "lint", prompt = "run linter" }, '
                '{ id = "review", prompt = "review the diff", '
                'agent = "kimi" }'
            )
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    pipeline = load_pipeline(repo)
    assert pipeline is not None
    assert pipeline.id == "ship"
    assert [stage.id for stage in pipeline.stages] == ["lint", "review"]
    assert pipeline.stages[0].prompt == "run linter"
    assert pipeline.stages[1].agent == "kimi"


def test_missing_pipeline_section_is_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    assert load_pipeline(repo) is None
    assert run_pipeline(repo) == []


def test_run_stages_in_listed_order_dispatches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=_pipeline_extra(
            stages=(
                '{ id = "review", prompt = "review the diff", '
                'agent = "kimi" }, '
                '{ id = "lint", prompt = "run linter" }'
            )
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    ran = run_pipeline(
        repo,
        bus=bus,
        store=store,
        audit=AuditLog(home),
    )
    assert [stage.id for stage in ran] == ["review", "lint"]
    first = bus.read(QUEUE_TASKS, visibility_timeout=600)
    second = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert first is not None
    assert second is not None
    assert first.task_id.startswith("ship:review:")
    UUID(first.task_id.rsplit(":", 1)[-1])
    assert first.prompt == "review the diff"
    assert first.agent == "kimi"
    assert second.task_id.startswith("ship:lint:")
    UUID(second.task_id.rsplit(":", 1)[-1])
    assert second.prompt == "run linter"
    assert second.agent == "grok"
    assert first.task_id != second.task_id
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert len(list((home / "sessions").glob("*.json"))) == 2


def test_unique_task_id_per_stage_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=_pipeline_extra(
            stages='{ id = "lint", prompt = "run linter" }'
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    run_pipeline(repo, bus=bus, store=store, audit=AuditLog(home))
    run_pipeline(repo, bus=bus, store=store, audit=AuditLog(home))
    first = bus.read(QUEUE_TASKS, visibility_timeout=600)
    second = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert first is not None
    assert second is not None
    assert first.task_id != second.task_id
    assert first.task_id.startswith("ship:lint:")
    assert second.task_id.startswith("ship:lint:")


def test_injected_run_uses_listed_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=_pipeline_extra(
            stages=(
                '{ id = "review", prompt = "review the diff" }, '
                '{ id = "lint", prompt = "run linter" }'
            )
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    seen: list[str] = []

    def _run(stage: object) -> None:
        seen.append(getattr(stage, "id"))

    ran = run_pipeline(repo, bus=bus, run=_run, audit=AuditLog(home))
    assert [stage.id for stage in ran] == ["review", "lint"]
    assert seen == ["review", "lint"]
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert list((home / "sessions").glob("*.json")) == []


@pytest.mark.parametrize("field", ["needs", "depends"])
def test_graph_edge_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, field: str
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=_pipeline_extra(
            stages=(
                '{ id = "review", prompt = "review the diff", '
                f'{field} = ["lint"] }}'
            )
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    with pytest.raises(PolicyDenied):
        load_pipeline(repo)
    with pytest.raises(PolicyDenied):
        run_pipeline(
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
        extra=_pipeline_extra(
            stages=(
                '{ id = "lint", prompt = "run linter" }, '
                '{ id = "review", prompt = "review the diff", '
                'agent = "kimi" }'
            )
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    with pytest.raises(PolicyDenied):
        run_pipeline(
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


def test_raw_key_in_stages_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=_pipeline_extra(
            stages=(
                '{ id = "lint", prompt = "run linter", '
                'key = "sk-secret-value" }'
            )
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with pytest.raises(PolicyDenied):
        load_pipeline(repo)
    bus = Bus()
    store = SessionStore(home)
    with pytest.raises(PolicyDenied):
        run_pipeline(
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
        + _pipeline_extra(
            stages=(
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
        run_pipeline(
            repo,
            bus=bus,
            store=store,
            audit=AuditLog(home),
        )
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert list((home / "sessions").glob("*.json")) == []
