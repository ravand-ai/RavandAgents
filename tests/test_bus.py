"""Bus seam: send/read/heartbeat/ack (GitHub issue #131).

Source of law: docs/HLD.md Bus primitives, docs/SCHEMA.md TaskMessage,
docs/MODULAR.md bus seam. In-memory fake only. No Postgres. No Kafka.
"""

from __future__ import annotations

import pytest

from ravand_bus import FailClosed, TaskMessage, Bus

FORBIDDEN = ("sk-", "xai-", "Bearer", "cookie")

QUEUE_TASKS = "q.tasks"
QUEUE_EVENTS = "q.events"
QUEUE_RESULTS = "q.results"


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def _task(**overrides: object) -> TaskMessage:
    payload: dict[str, object] = {
        "task_id": "task-1",
        "cwd_hint": "/repo",
        "profile": "work",
        "agent": "grok",
        "prompt": "ship the bus seam",
        "permissions": "repo-only",
    }
    payload.update(overrides)
    return TaskMessage(**payload)  # type: ignore[arg-type]


def test_send_then_read_returns_task_message() -> None:
    bus = Bus()
    message = _task(
        traceparent="00-trace",
        repo="https://git.example/acme",
        ref="main",
        overflow="kimi",
        created_by="ali",
    )
    bus.send(QUEUE_TASKS, message)
    got = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert got == message
    assert got.task_id == "task-1"
    assert got.cwd_hint == "/repo"
    assert got.profile == "work"
    assert got.agent == "grok"
    assert got.overflow == "kimi"
    assert got.prompt == "ship the bus seam"
    assert got.permissions == "repo-only"
    assert got.created_by == "ali"


def test_read_empty_queue_returns_none() -> None:
    bus = Bus()
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None


def test_visibility_timeout_hides_until_timeout() -> None:
    clock = _Clock()
    bus = Bus(monotonic=clock)
    bus.send(QUEUE_TASKS, _task())
    first = bus.read(QUEUE_TASKS, visibility_timeout=10)
    assert first is not None
    assert bus.read(QUEUE_TASKS, visibility_timeout=10) is None
    clock.value = 9.0
    assert bus.read(QUEUE_TASKS, visibility_timeout=10) is None
    clock.value = 10.0
    again = bus.read(QUEUE_TASKS, visibility_timeout=10)
    assert again == first


def test_heartbeat_extends_visibility() -> None:
    clock = _Clock()
    bus = Bus(monotonic=clock)
    bus.send(QUEUE_TASKS, _task())
    got = bus.read(QUEUE_TASKS, visibility_timeout=10)
    assert got is not None
    clock.value = 5.0
    bus.heartbeat(got, visibility_timeout=10)
    clock.value = 14.0
    assert bus.read(QUEUE_TASKS, visibility_timeout=10) is None
    clock.value = 15.0
    again = bus.read(QUEUE_TASKS, visibility_timeout=10)
    assert again == got


def test_archive_removes_message() -> None:
    clock = _Clock()
    bus = Bus(monotonic=clock)
    bus.send(QUEUE_TASKS, _task())
    got = bus.read(QUEUE_TASKS, visibility_timeout=10)
    assert got is not None
    bus.archive(got)
    clock.value = 100.0
    assert bus.read(QUEUE_TASKS, visibility_timeout=10) is None


def test_ack_success_removes_message() -> None:
    clock = _Clock()
    bus = Bus(monotonic=clock)
    bus.send(QUEUE_TASKS, _task())
    got = bus.read(QUEUE_TASKS, visibility_timeout=10)
    assert got is not None
    bus.ack(got, success=True)
    clock.value = 100.0
    assert bus.read(QUEUE_TASKS, visibility_timeout=10) is None


def test_ack_fail_makes_message_visible() -> None:
    clock = _Clock()
    bus = Bus(monotonic=clock)
    bus.send(QUEUE_TASKS, _task())
    got = bus.read(QUEUE_TASKS, visibility_timeout=10)
    assert got is not None
    bus.ack(got, success=False)
    again = bus.read(QUEUE_TASKS, visibility_timeout=10)
    assert again == got


def test_poison_after_inspect_removes_message() -> None:
    clock = _Clock()
    bus = Bus(monotonic=clock)
    bus.send(QUEUE_TASKS, _task())
    got = bus.read(QUEUE_TASKS, visibility_timeout=10)
    assert got is not None
    bus.poison(got)
    clock.value = 100.0
    assert bus.read(QUEUE_TASKS, visibility_timeout=10) is None


@pytest.mark.parametrize("queue", [QUEUE_TASKS, QUEUE_EVENTS, QUEUE_RESULTS])
def test_named_queues_accept_send_and_read(queue: str) -> None:
    bus = Bus()
    message = _task(task_id=f"task-{queue}")
    bus.send(queue, message)
    assert bus.read(queue, visibility_timeout=600) == message


def test_unknown_queue_fails_closed() -> None:
    bus = Bus()
    with pytest.raises(FailClosed):
        bus.send("q.unknown", _task())
    with pytest.raises(FailClosed):
        bus.read("q.unknown", visibility_timeout=600)


@pytest.mark.parametrize(
    "overrides",
    [
        {"prompt": "token sk-secret-value must not queue"},
        {"prompt": "xai-secret"},
        {"prompt": "Authorization Bearer abc"},
        {"prompt": "vendor cookies file"},
        {"prompt": "HOME=/home/u/.claude"},
        {"cwd_hint": "~/.ravand/profiles/work"},
        {"created_by": "sk-user"},
        {"repo": "see ~/.grok/cookies"},
    ],
)
def test_secret_fields_fail_closed(overrides: dict[str, str]) -> None:
    with pytest.raises(FailClosed):
        _task(**overrides)


def test_send_rejects_secret_payload() -> None:
    bus = Bus()
    with pytest.raises(FailClosed):
        bus.send(QUEUE_TASKS, _task(prompt="do not leak Bearer tokens"))
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    for marker in FORBIDDEN:
        with pytest.raises(FailClosed):
            _task(prompt=f"payload has {marker} inside")
