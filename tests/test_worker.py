"""Worker process: read, heartbeat, archive (GitHub issue #134).

Drain and cordon (GitHub issue #146): cordon nacks without run;
drain finishes in-flight then stops.

ravand serve worker loop (GitHub issue #212): loop run_once with
injected sleep and max_ticks. capability_miss stays.

Source of law: docs/HLD.md Worker, docs/SCHEMA.md TaskMessage.
Injected bus and run stub. No Kubernetes. Queue does not ship git.
No Kafka. No TUI.
"""

from __future__ import annotations

import json
import subprocess
import threading
from pathlib import Path

import pytest

from ravand_audit import AuditLog
from ravand_bus import Bus, TaskMessage
from ravand_runtime.worker import FailClosed, Worker, serve_worker

ROOT = Path(__file__).resolve().parents[1]
QUEUE_TASKS = "q.tasks"


def _ravand(*args: str, cwd: Path | None = None, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "ravand", *args],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=15,
    )


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


def _audit_events(root: Path) -> list[dict[str, object]]:
    path = root / "audit.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_cordon_nacks_new_jobs_without_run(tmp_path: Path) -> None:
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
    worker = Worker(bus, run=run, audit=log)
    worker.cordon()
    assert worker.run_once() is True
    assert ran == []
    assert beats["n"] == 0
    again = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert again == message
    events = _audit_events(tmp_path)
    assert len(events) == 1
    assert events[0]["type"] == "worker.cordoned"
    assert events[0]["taskId"] == "task-1"
    assert events[0]["profile"] == "work"
    assert events[0]["agent"] == "grok"
    assert events[0]["cwd"] == str(tmp_path)
    blob = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "ship the worker loop" not in blob


def test_drain_when_idle_stops_without_taking_jobs(tmp_path: Path) -> None:
    bus = Bus()
    message = _task(str(tmp_path))
    bus.send(QUEUE_TASKS, message)
    ran: list[TaskMessage] = []

    def run(got: TaskMessage) -> int:
        ran.append(got)
        return 0

    worker = Worker(bus, run=run)
    worker.drain()
    assert worker.run_once() is False
    assert ran == []
    again = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert again == message


def test_drain_finishes_inflight_then_stops(tmp_path: Path) -> None:
    bus = Bus()
    first = _task(str(tmp_path), task_id="task-1")
    second = _task(str(tmp_path), task_id="task-2", prompt="second job")
    bus.send(QUEUE_TASKS, first)
    bus.send(QUEUE_TASKS, second)
    started = threading.Event()
    release = threading.Event()
    ran: list[str] = []

    def run(got: TaskMessage) -> int:
        ran.append(got.task_id)
        started.set()
        assert release.wait(timeout=5.0)
        return 0

    worker = Worker(bus, run=run)
    errors: list[BaseException] = []

    def once() -> None:
        try:
            assert worker.run_once() is True
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    thread = threading.Thread(target=once)
    thread.start()
    assert started.wait(timeout=5.0)
    drain_done = threading.Event()

    def do_drain() -> None:
        try:
            worker.drain()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)
        finally:
            drain_done.set()

    drain_thread = threading.Thread(target=do_drain)
    drain_thread.start()
    assert not drain_done.wait(timeout=0.2)
    release.set()
    thread.join(timeout=5.0)
    drain_thread.join(timeout=5.0)
    assert errors == []
    assert ran == ["task-1"]
    assert worker.run_once() is False
    assert ran == ["task-1"]
    leftover = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert leftover == second


def test_serve_worker_help_exists() -> None:
    result = _ravand("serve", "worker", "--help")
    assert result.returncode == 0, result.stderr
    combined = (result.stdout + result.stderr).lower()
    assert "usage" in combined
    assert "worker" in combined


def test_serve_worker_loop_uses_injected_interval(tmp_path: Path) -> None:
    bus = Bus()
    ran: list[TaskMessage] = []

    def run(got: TaskMessage) -> int:
        ran.append(got)
        return 0

    slept: list[float] = []
    code = serve_worker(
        bus=bus,
        run=run,
        interval=0,
        max_ticks=2,
        sleep=slept.append,
    )
    assert code == 0
    assert slept == [0]
    assert ran == []


def test_serve_worker_consumes_queued_task(tmp_path: Path) -> None:
    bus = Bus()
    message = _task(str(tmp_path))
    bus.send(QUEUE_TASKS, message)
    ran: list[TaskMessage] = []

    def run(got: TaskMessage) -> int:
        ran.append(got)
        return 0

    slept: list[float] = []
    code = serve_worker(
        bus=bus,
        run=run,
        interval=0,
        max_ticks=1,
        sleep=slept.append,
        audit=AuditLog(tmp_path),
    )
    assert code == 0
    assert ran == [message]
    assert all(seconds < 60 for seconds in slept)
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None


def test_serve_worker_capability_miss_still_nacks(tmp_path: Path) -> None:
    bus = Bus()
    message = _task(str(tmp_path))
    bus.send(QUEUE_TASKS, message)
    ran: list[TaskMessage] = []

    def run(got: TaskMessage) -> int:
        ran.append(got)
        return 0

    code = serve_worker(
        bus=bus,
        run=run,
        interval=0,
        max_ticks=1,
        sleep=lambda _seconds: None,
        auth_ok=False,
        audit=AuditLog(tmp_path),
    )
    assert code == 0
    assert ran == []
    again = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert again == message
    events = _audit_events(tmp_path)
    assert [event["type"] for event in events] == ["worker.capability_miss"]
    blob = (tmp_path / "audit.jsonl").read_text(encoding="utf-8")
    assert "ship the worker loop" not in blob


def test_serve_worker_missing_workspace_fails_closed(tmp_path: Path) -> None:
    bus = Bus()
    missing = tmp_path / "no-worktree"
    bus.send(QUEUE_TASKS, _task(str(missing)))
    ran: list[TaskMessage] = []

    def run(got: TaskMessage) -> int:
        ran.append(got)
        return 0

    code = serve_worker(
        bus=bus,
        run=run,
        interval=0,
        max_ticks=1,
        sleep=lambda _seconds: None,
        audit=AuditLog(tmp_path),
    )
    assert code != 0
    assert ran == []


def test_serve_worker_exits_when_drained_idle(tmp_path: Path) -> None:
    bus = Bus()
    message = _task(str(tmp_path))
    bus.send(QUEUE_TASKS, message)
    ran: list[TaskMessage] = []

    def run(got: TaskMessage) -> int:
        ran.append(got)
        return 0

    worker = Worker(bus, run=run, audit=AuditLog(tmp_path))

    def sleep(_seconds: float) -> None:
        worker.drain()

    code = serve_worker(
        worker=worker,
        interval=0,
        sleep=sleep,
    )
    assert code == 0
    assert ran == [message]
    leftover = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert leftover is None
