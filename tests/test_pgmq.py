"""PGMQ bus provider (GitHub issue #132).

Source of law: docs/HLD.md Bus primitives, docs/SCHEMA.md TaskMessage,
docs/MODULAR.md bus seam. Fake connection. No testcontainers. No Kafka.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from ravand_bus import FailClosed, PgmqBus, TaskMessage

FORBIDDEN = ("sk-", "xai-", "Bearer", "cookie")

QUEUE_TASKS = "q.tasks"
QUEUE_EVENTS = "q.events"
QUEUE_RESULTS = "q.results"

ROOT = Path(__file__).resolve().parents[1]


class _Cursor:
    def __init__(self, row: tuple | None) -> None:
        self._row = row

    def fetchone(self) -> tuple | None:
        return self._row


class FakeConnection:
    """Records PGMQ SQL. Stores payloads so send/read can round-trip."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self._next_id = 1
        self._messages: dict[int, dict] = {}

    def execute(self, sql: str, params: tuple | None = None) -> _Cursor:
        params = tuple(params or ())
        self.calls.append((sql, params))
        lowered = sql.lower()
        if "pgmq.send" in lowered:
            msg_id = self._next_id
            self._next_id += 1
            payload = params[1]
            if isinstance(payload, str):
                payload = json.loads(payload)
            self._messages[msg_id] = {
                "queue": params[0],
                "payload": payload,
                "visible": True,
            }
            return _Cursor((msg_id,))
        if "pgmq.read" in lowered:
            queue = params[0]
            for msg_id, rec in self._messages.items():
                if rec["queue"] == queue and rec["visible"]:
                    rec["visible"] = False
                    return _Cursor((msg_id, rec["payload"]))
            return _Cursor(None)
        if "pgmq.set_vt" in lowered:
            msg_id = int(params[1])
            vt = int(params[2])
            rec = self._messages.get(msg_id)
            if rec is not None:
                rec["visible"] = vt == 0
            return _Cursor((msg_id,))
        if "pgmq.archive" in lowered or "pgmq.delete" in lowered:
            msg_id = int(params[1])
            self._messages.pop(msg_id, None)
            return _Cursor((True,))
        return _Cursor(None)


class _Boom:
    def execute(self, sql: str, params: tuple | None = None) -> _Cursor:
        raise OSError("connection refused")


def _task(**overrides: object) -> TaskMessage:
    payload: dict[str, object] = {
        "task_id": "task-1",
        "cwd_hint": "/repo",
        "profile": "work",
        "agent": "grok",
        "prompt": "ship the pgmq provider",
        "permissions": "repo-only",
    }
    payload.update(overrides)
    return TaskMessage(**payload)  # type: ignore[arg-type]


def _calls_with(conn: FakeConnection, name: str) -> list[tuple[str, tuple]]:
    return [(sql, params) for sql, params in conn.calls if name in sql.lower()]


def test_ensure_queues_calls_pgmq_create() -> None:
    conn = FakeConnection()
    PgmqBus(connection=conn)
    created = [params[0] for sql, params in _calls_with(conn, "pgmq.create")]
    assert "q_tasks" in created
    assert "q_events" in created
    assert "q_results" in created
    for sql, params in _calls_with(conn, "pgmq.create"):
        assert "%s" in sql
        assert "q.tasks" not in sql
        assert params[0] in {"q_tasks", "q_events", "q_results"}


def test_send_then_read_returns_task_message() -> None:
    conn = FakeConnection()
    bus = PgmqBus(connection=conn)
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
    assert got is not None
    assert got.task_id == "task-1"
    assert got.cwd_hint == "/repo"
    assert got.profile == "work"
    assert got.agent == "grok"
    assert got.overflow == "kimi"
    assert got.prompt == "ship the pgmq provider"
    assert got.permissions == "repo-only"
    assert got.created_by == "ali"
    send_sql, send_params = _calls_with(conn, "pgmq.send")[-1]
    assert "pgmq.send" in send_sql.lower()
    assert "%s" in send_sql
    assert send_params[0] == "q_tasks"
    payload = send_params[1]
    if isinstance(payload, str):
        payload = json.loads(payload)
    assert payload["task_id"] == "task-1"
    assert payload["repo"] == "https://git.example/acme"
    read_sql, read_params = _calls_with(conn, "pgmq.read")[-1]
    assert "pgmq.read" in read_sql.lower()
    assert "%s" in read_sql
    assert read_params[0] == "q_tasks"
    assert 600 in read_params


def test_read_empty_queue_returns_none() -> None:
    conn = FakeConnection()
    bus = PgmqBus(connection=conn)
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert _calls_with(conn, "pgmq.read")


def test_read_hides_until_visibility_timeout_expires() -> None:
    conn = FakeConnection()
    bus = PgmqBus(connection=conn)
    bus.send(QUEUE_TASKS, _task())
    first = bus.read(QUEUE_TASKS, visibility_timeout=10)
    assert first is not None
    assert bus.read(QUEUE_TASKS, visibility_timeout=10) is None


def test_heartbeat_sql_uses_pgmq_set_vt() -> None:
    conn = FakeConnection()
    bus = PgmqBus(connection=conn)
    bus.send(QUEUE_TASKS, _task())
    got = bus.read(QUEUE_TASKS, visibility_timeout=10)
    assert got is not None
    bus.heartbeat(got, visibility_timeout=10)
    sql, params = _calls_with(conn, "pgmq.set_vt")[-1]
    assert "pgmq.set_vt" in sql.lower()
    assert "%s" in sql
    assert params[0] == "q_tasks"
    assert params[2] == 10
    assert bus.read(QUEUE_TASKS, visibility_timeout=10) is None


def test_archive_sql_uses_pgmq_archive() -> None:
    conn = FakeConnection()
    bus = PgmqBus(connection=conn)
    bus.send(QUEUE_TASKS, _task())
    got = bus.read(QUEUE_TASKS, visibility_timeout=10)
    assert got is not None
    bus.archive(got)
    sql, params = _calls_with(conn, "pgmq.archive")[-1]
    assert "pgmq.archive" in sql.lower()
    assert "%s" in sql
    assert params[0] == "q_tasks"
    assert bus.read(QUEUE_TASKS, visibility_timeout=10) is None


def test_ack_success_sql_uses_pgmq_archive() -> None:
    conn = FakeConnection()
    bus = PgmqBus(connection=conn)
    bus.send(QUEUE_TASKS, _task())
    got = bus.read(QUEUE_TASKS, visibility_timeout=10)
    assert got is not None
    bus.ack(got, success=True)
    sql, params = _calls_with(conn, "pgmq.archive")[-1]
    assert "pgmq.archive" in sql.lower()
    assert params[0] == "q_tasks"
    assert bus.read(QUEUE_TASKS, visibility_timeout=10) is None


def test_ack_fail_makes_message_visible() -> None:
    conn = FakeConnection()
    bus = PgmqBus(connection=conn)
    bus.send(QUEUE_TASKS, _task())
    got = bus.read(QUEUE_TASKS, visibility_timeout=10)
    assert got is not None
    bus.ack(got, success=False)
    sql, params = _calls_with(conn, "pgmq.set_vt")[-1]
    assert "pgmq.set_vt" in sql.lower()
    assert params[0] == "q_tasks"
    assert params[2] == 0
    again = bus.read(QUEUE_TASKS, visibility_timeout=10)
    assert again == got


def test_poison_sql_uses_pgmq_delete() -> None:
    conn = FakeConnection()
    bus = PgmqBus(connection=conn)
    bus.send(QUEUE_TASKS, _task())
    got = bus.read(QUEUE_TASKS, visibility_timeout=10)
    assert got is not None
    bus.poison(got)
    sql, params = _calls_with(conn, "pgmq.delete")[-1]
    assert "pgmq.delete" in sql.lower()
    assert "%s" in sql
    assert params[0] == "q_tasks"
    assert bus.read(QUEUE_TASKS, visibility_timeout=10) is None


@pytest.mark.parametrize("queue", [QUEUE_TASKS, QUEUE_EVENTS, QUEUE_RESULTS])
def test_named_queues_map_to_pgmq_safe_names(queue: str) -> None:
    conn = FakeConnection()
    bus = PgmqBus(connection=conn)
    message = _task(task_id=f"task-{queue}")
    bus.send(queue, message)
    assert bus.read(queue, visibility_timeout=600) == message
    pgmq_name = queue.replace(".", "_")
    send_sql, send_params = _calls_with(conn, "pgmq.send")[-1]
    assert send_params[0] == pgmq_name
    assert queue not in send_sql
    read_sql, read_params = _calls_with(conn, "pgmq.read")[-1]
    assert read_params[0] == pgmq_name
    assert queue not in read_sql


def test_same_repo_messages_stay_on_one_queue() -> None:
    conn = FakeConnection()
    bus = PgmqBus(connection=conn)
    first = _task(task_id="task-a", repo="https://git.example/acme")
    second = _task(task_id="task-b", repo="https://git.example/acme")
    bus.send(QUEUE_TASKS, first)
    bus.send(QUEUE_TASKS, second)
    send_queues = [params[0] for _sql, params in _calls_with(conn, "pgmq.send")]
    assert send_queues == ["q_tasks", "q_tasks"]
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) == first
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) == second


def test_unknown_queue_fails_closed() -> None:
    conn = FakeConnection()
    bus = PgmqBus(connection=conn)
    with pytest.raises(FailClosed):
        bus.send("q.unknown", _task())
    with pytest.raises(FailClosed):
        bus.read("q.unknown", visibility_timeout=600)
    for _sql, params in conn.calls:
        assert "q.unknown" not in params
        assert "q_unknown" not in params


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
    conn = FakeConnection()
    bus = PgmqBus(connection=conn)
    with pytest.raises(FailClosed):
        bus.send(QUEUE_TASKS, _task(**overrides))
    assert _calls_with(conn, "pgmq.send") == []


def test_send_rejects_secret_payload() -> None:
    conn = FakeConnection()
    bus = PgmqBus(connection=conn)
    with pytest.raises(FailClosed):
        bus.send(QUEUE_TASKS, _task(prompt="do not leak Bearer tokens"))
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    for marker in FORBIDDEN:
        with pytest.raises(FailClosed):
            bus.send(QUEUE_TASKS, _task(prompt=f"payload has {marker} inside"))
    assert _calls_with(conn, "pgmq.send") == []


def test_unreachable_execute_fails_closed() -> None:
    with pytest.raises(FailClosed):
        PgmqBus(connection=_Boom())


def test_configured_url_unreachable_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Psycopg:
        @staticmethod
        def connect(url: str, **kwargs: object) -> object:
            raise OSError("refused")

    monkeypatch.setitem(sys.modules, "psycopg", _Psycopg())
    with pytest.raises(FailClosed):
        PgmqBus(url="postgresql://example.invalid/ravand")


def test_policy_and_runtime_do_not_import_psycopg() -> None:
    for package in ("policy", "runtime"):
        root = ROOT / "packages" / package
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".toml"}:
                continue
            text = path.read_text(encoding="utf-8")
            assert "psycopg" not in text, f"{path} must not mention psycopg"
