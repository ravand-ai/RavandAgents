"""Postgres + PGMQ provider of the Bus seam."""

from __future__ import annotations

import json
from dataclasses import fields

from ravand_bus import FailClosed, QUEUES, TaskMessage, _refuse_secrets, _scan_message


def _pgmq_queue(queue: str) -> str:
    if queue not in QUEUES:
        raise FailClosed(f"unknown bus queue: {queue!r}")
    return queue.replace(".", "_")


def _payload(message: TaskMessage) -> dict[str, str]:
    payload: dict[str, str] = {}
    for item in fields(message):
        value = getattr(message, item.name)
        if value is None:
            continue
        payload[item.name] = value
    return payload


def _opt(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _from_payload(payload: dict) -> TaskMessage:
    return TaskMessage(
        task_id=str(payload["task_id"]),
        cwd_hint=str(payload["cwd_hint"]),
        profile=str(payload["profile"]),
        agent=str(payload["agent"]),
        prompt=str(payload["prompt"]),
        permissions=str(payload["permissions"]),
        traceparent=_opt(payload.get("traceparent")),
        repo=_opt(payload.get("repo")),
        ref=_opt(payload.get("ref")),
        overflow=_opt(payload.get("overflow")),
        created_by=_opt(payload.get("created_by")),
    )


def _connect(url: str) -> object:
    try:
        import psycopg

        return psycopg.connect(url, autocommit=True)
    except Exception as exc:
        raise FailClosed("bus unreachable") from exc


class PgmqBus:
    """Postgres + PGMQ provider of the Bus seam."""

    def __init__(
        self,
        *,
        url: str | None = None,
        connection: object | None = None,
    ) -> None:
        if connection is not None:
            self._conn = connection
        elif url is not None:
            self._conn = _connect(url)
        else:
            raise FailClosed("bus is not configured")
        self._in_flight: dict[TaskMessage, tuple[str, int]] = {}
        for name in QUEUES:
            self._execute("SELECT pgmq.create(%s)", (_pgmq_queue(name),))

    def _execute(self, sql: str, params: tuple) -> object:
        try:
            return self._conn.execute(sql, params)
        except FailClosed:
            raise
        except Exception as exc:
            raise FailClosed("bus unreachable") from exc

    def _fetchone(self, sql: str, params: tuple) -> tuple | None:
        cursor = self._execute(sql, params)
        try:
            return cursor.fetchone()
        except FailClosed:
            raise
        except Exception as exc:
            raise FailClosed("bus unreachable") from exc

    def _require_in_flight(self, message: TaskMessage) -> tuple[str, int]:
        found = self._in_flight.get(message)
        if found is None:
            raise FailClosed("bus message is not in flight")
        return found

    def send(self, queue: str, message: TaskMessage) -> None:
        if not isinstance(message, TaskMessage):
            raise FailClosed("bus payload must be TaskMessage")
        _scan_message(message)
        name = _pgmq_queue(queue)
        blob = json.dumps(_payload(message), separators=(",", ":"))
        _refuse_secrets(blob)
        self._execute("SELECT pgmq.send(%s, %s::jsonb)", (name, blob))

    def read(
        self, queue: str, *, visibility_timeout: float = 600
    ) -> TaskMessage | None:
        name = _pgmq_queue(queue)
        row = self._fetchone(
            "SELECT msg_id, message FROM pgmq.read(%s, %s, %s)",
            (name, int(visibility_timeout), 1),
        )
        if row is None:
            return None
        raw = row[1]
        try:
            if isinstance(raw, str):
                payload = json.loads(raw)
            else:
                payload = dict(raw)
            message = _from_payload(payload)
        except FailClosed:
            raise
        except (TypeError, ValueError, KeyError) as exc:
            raise FailClosed("bus payload is invalid") from exc
        self._in_flight[message] = (name, int(row[0]))
        return message

    def heartbeat(
        self, message: TaskMessage, *, visibility_timeout: float = 600
    ) -> None:
        name, msg_id = self._require_in_flight(message)
        self._execute(
            "SELECT pgmq.set_vt(%s, %s, %s)",
            (name, msg_id, int(visibility_timeout)),
        )

    def archive(self, message: TaskMessage) -> None:
        name, msg_id = self._require_in_flight(message)
        self._execute("SELECT pgmq.archive(%s, %s)", (name, msg_id))
        del self._in_flight[message]

    def ack(self, message: TaskMessage, *, success: bool) -> None:
        name, msg_id = self._require_in_flight(message)
        if success:
            self._execute("SELECT pgmq.archive(%s, %s)", (name, msg_id))
            del self._in_flight[message]
            return
        self._execute("SELECT pgmq.set_vt(%s, %s, %s)", (name, msg_id, 0))
        del self._in_flight[message]

    def poison(self, message: TaskMessage) -> None:
        name, msg_id = self._require_in_flight(message)
        self._execute("SELECT pgmq.delete(%s, %s)", (name, msg_id))
        del self._in_flight[message]
