"""Worker skips jobs the local profile cannot run (GitHub issue #135).

Source of law: docs/HLD.md Worker, docs/SCHEMA.md worker.capability_miss.
Injected auth_ok and allowed_agents. No live CLI. No Kubernetes.
"""

from __future__ import annotations

import json
from pathlib import Path

from ravand_audit import AuditLog
from ravand_bus import Bus, TaskMessage
from ravand_runtime.worker import Worker

QUEUE_TASKS = "q.tasks"


def _task(cwd_hint: str, **overrides: object) -> TaskMessage:
    payload: dict[str, object] = {
        "task_id": "task-1",
        "cwd_hint": cwd_hint,
        "profile": "work",
        "agent": "grok",
        "prompt": "ship the worker loop",
        "permissions": "repo-only",
    }
    payload.update(overrides)
    return TaskMessage(**payload)  # type: ignore[arg-type]


def _audit_events(root: Path) -> list[dict[str, object]]:
    path = root / "audit.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_auth_not_ok_nacks_and_audits_without_run(tmp_path: Path) -> None:
    bus = Bus()
    message = _task(str(tmp_path))
    bus.send(QUEUE_TASKS, message)
    ran: list[TaskMessage] = []
    beats = {"n": 0}
    orig_heartbeat = bus.heartbeat

    def heartbeat(
        got: TaskMessage, *, visibility_timeout: float = 600
    ) -> None:
        beats["n"] += 1
        orig_heartbeat(got, visibility_timeout=visibility_timeout)

    bus.heartbeat = heartbeat  # type: ignore[method-assign]

    def run(got: TaskMessage) -> int:
        ran.append(got)
        return 0

    log = AuditLog(tmp_path)
    worker = Worker(bus, run=run, auth_ok=False, audit=log)
    assert worker.run_once() is True
    assert ran == []
    assert beats["n"] == 0
    again = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert again == message
    events = _audit_events(tmp_path)
    assert len(events) == 1
    assert events[0]["type"] == "worker.capability_miss"
    assert events[0]["taskId"] == "task-1"
    assert events[0]["profile"] == "work"
    assert events[0]["agent"] == "grok"
    assert events[0]["cwd"] == str(tmp_path)
    blob = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "ship the worker loop" not in blob


def test_agent_not_allowed_nacks_and_audits_without_run(tmp_path: Path) -> None:
    bus = Bus()
    message = _task(str(tmp_path))
    bus.send(QUEUE_TASKS, message)
    ran: list[TaskMessage] = []

    def run(got: TaskMessage) -> int:
        ran.append(got)
        return 0

    log = AuditLog(tmp_path)
    worker = Worker(
        bus,
        run=run,
        auth_ok=True,
        allowed_agents=frozenset({"kimi"}),
        audit=log,
    )
    assert worker.run_once() is True
    assert ran == []
    again = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert again == message
    events = _audit_events(tmp_path)
    assert [event["type"] for event in events] == ["worker.capability_miss"]
    assert events[0]["agent"] == "grok"


def test_allowed_agent_with_auth_ok_runs(tmp_path: Path) -> None:
    bus = Bus()
    message = _task(str(tmp_path))
    bus.send(QUEUE_TASKS, message)
    ran: list[TaskMessage] = []

    def run(got: TaskMessage) -> int:
        ran.append(got)
        return 0

    log = AuditLog(tmp_path)
    worker = Worker(
        bus,
        run=run,
        auth_ok=True,
        allowed_agents=frozenset({"grok"}),
        audit=log,
    )
    assert worker.run_once() is True
    assert ran == [message]
    assert _audit_events(tmp_path) == []
    clock_read = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert clock_read is None
