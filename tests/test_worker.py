"""Worker process: read, heartbeat, archive (GitHub issue #134).

Source of law: docs/HLD.md Worker, docs/SCHEMA.md TaskMessage.
Injected bus and run stub. No Kubernetes. Queue does not ship git.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ravand_bus import Bus, TaskMessage
from ravand_runtime.worker import FailClosed, Worker

QUEUE_TASKS = "q.tasks"


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


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


def test_empty_queue_does_not_run() -> None:
    bus = Bus()
    ran: list[TaskMessage] = []

    def run(message: TaskMessage) -> int:
        ran.append(message)
        return 0

    worker = Worker(bus, run=run)
    assert worker.run_once() is False
    assert ran == []


def test_read_q_tasks_runs_stub_and_archives(tmp_path: Path) -> None:
    clock = _Clock()
    bus = Bus(monotonic=clock)
    message = _task(str(tmp_path))
    bus.send(QUEUE_TASKS, message)
    seen: dict[str, object] = {}
    orig_read = bus.read

    def read(queue: str, *, visibility_timeout: float = 600) -> TaskMessage | None:
        seen["queue"] = queue
        seen["vt"] = visibility_timeout
        return orig_read(queue, visibility_timeout=visibility_timeout)

    bus.read = read  # type: ignore[method-assign]
    ran: list[TaskMessage] = []

    def run(got: TaskMessage) -> int:
        ran.append(got)
        return 0

    worker = Worker(bus, run=run)
    assert worker.run_once() is True
    assert seen["queue"] == QUEUE_TASKS
    assert seen["vt"] == 600
    assert ran == [message]
    clock.value = 1000.0
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None


def test_heartbeat_while_run_is_live(tmp_path: Path) -> None:
    bus = Bus()
    bus.send(QUEUE_TASKS, _task(str(tmp_path)))
    beats = {"n": 0}
    orig = bus.heartbeat

    def heartbeat(
        message: TaskMessage, *, visibility_timeout: float = 600
    ) -> None:
        beats["n"] += 1
        orig(message, visibility_timeout=visibility_timeout)

    bus.heartbeat = heartbeat  # type: ignore[method-assign]

    def run(message: TaskMessage) -> int:
        assert beats["n"] >= 1
        return 0

    Worker(bus, run=run).run_once()
    assert beats["n"] >= 1


def test_ack_on_terminal_error(tmp_path: Path) -> None:
    bus = Bus()
    message = _task(str(tmp_path))
    bus.send(QUEUE_TASKS, message)

    def run(got: TaskMessage) -> int:
        return 5

    Worker(bus, run=run).run_once()
    again = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert again == message


def test_missing_workspace_fails_closed(tmp_path: Path) -> None:
    bus = Bus()
    missing = tmp_path / "no-worktree"
    bus.send(QUEUE_TASKS, _task(str(missing)))
    ran: list[TaskMessage] = []

    def run(message: TaskMessage) -> int:
        ran.append(message)
        return 0

    worker = Worker(bus, run=run)
    with pytest.raises(FailClosed, match="workspace"):
        worker.run_once()
    assert ran == []
