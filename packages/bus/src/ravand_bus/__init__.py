"""Bus seam: send, read, heartbeat, archive/ack, poison. In-memory fake."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from dataclasses import dataclass, fields

QUEUES = frozenset({"q.tasks", "q.events", "q.results"})
_TOKEN_RE = re.compile(r"(?<![A-Za-z0-9])(?:sk-|xai-|Bearer)")
_COOKIE_MARKERS = ("cookie", ".grok/", ".kimi/", ".cursor/", ".claude")
_HOME_MARKERS = ("HOME=", "~/.ravand")


class FailClosed(Exception):
    """Bus could not allow the action."""


def _refuse_secrets(text: str) -> None:
    if _TOKEN_RE.search(text):
        raise FailClosed("bus refuses tokens")
    lowered = text.lower()
    for marker in _COOKIE_MARKERS:
        if marker in lowered:
            raise FailClosed("bus refuses cookie paths")
    for marker in _HOME_MARKERS:
        if marker in text:
            raise FailClosed("bus refuses HOME paths")


def _scan_message(message: TaskMessage) -> None:
    for item in fields(message):
        value = getattr(message, item.name)
        if value is None:
            continue
        if not isinstance(value, str) or not value.strip():
            raise FailClosed(f"task message {item.name} must be text")
        _refuse_secrets(value)


@dataclass(frozen=True)
class TaskMessage:
    task_id: str
    cwd_hint: str
    profile: str
    agent: str
    prompt: str
    permissions: str
    traceparent: str | None = None
    repo: str | None = None
    ref: str | None = None
    overflow: str | None = None
    created_by: str | None = None

    def __post_init__(self) -> None:
        _scan_message(self)


@dataclass
class _Entry:
    message: TaskMessage
    visible_at: float
    in_flight: bool = False


class Bus:
    """In-memory provider of the Bus seam. No Postgres. No Kafka."""

    def __init__(self, *, monotonic: Callable[[], float] | None = None) -> None:
        self._monotonic = monotonic or time.monotonic
        self._queues: dict[str, list[_Entry]] = {name: [] for name in QUEUES}

    def _require_queue(self, queue: str) -> list[_Entry]:
        entries = self._queues.get(queue)
        if entries is None:
            raise FailClosed(f"unknown bus queue: {queue!r}")
        return entries

    def send(self, queue: str, message: TaskMessage) -> None:
        if not isinstance(message, TaskMessage):
            raise FailClosed("bus payload must be TaskMessage")
        _scan_message(message)
        entries = self._require_queue(queue)
        entries.append(_Entry(message=message, visible_at=self._monotonic()))

    def read(
        self, queue: str, *, visibility_timeout: float = 600
    ) -> TaskMessage | None:
        entries = self._require_queue(queue)
        now = self._monotonic()
        for entry in entries:
            if entry.visible_at <= now:
                entry.visible_at = now + visibility_timeout
                entry.in_flight = True
                return entry.message
        return None

    def _in_flight(self, message: TaskMessage) -> _Entry:
        for entries in self._queues.values():
            for entry in entries:
                if entry.in_flight and entry.message == message:
                    return entry
        raise FailClosed("bus message is not in flight")

    def heartbeat(
        self, message: TaskMessage, *, visibility_timeout: float = 600
    ) -> None:
        entry = self._in_flight(message)
        entry.visible_at = self._monotonic() + visibility_timeout

    def archive(self, message: TaskMessage) -> None:
        self._remove(self._in_flight(message))

    def ack(self, message: TaskMessage, *, success: bool) -> None:
        entry = self._in_flight(message)
        if success:
            self._remove(entry)
            return
        entry.in_flight = False
        entry.visible_at = self._monotonic()

    def poison(self, message: TaskMessage) -> None:
        self._remove(self._in_flight(message))

    def _remove(self, entry: _Entry) -> None:
        for entries in self._queues.values():
            if entry in entries:
                entries.remove(entry)
                return
        raise FailClosed("bus message is missing")


__all__ = ["Bus", "FailClosed", "QUEUES", "TaskMessage"]
