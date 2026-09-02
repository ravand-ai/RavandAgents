"""Worker: read q.tasks, heartbeat while live, archive or ack."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from ravand_audit import AuditLog
from ravand_bus import TaskMessage
from ravand_policy import ravand_home

QUEUE_TASKS = "q.tasks"
_VISIBILITY_TIMEOUT = 600
_HEARTBEAT_INTERVAL = 30.0


class FailClosed(Exception):
    """Worker could not allow the action."""


class Worker:
    """One process: read q.tasks, run, heartbeat, archive or ack."""

    def __init__(
        self,
        bus: object,
        *,
        run: Callable[[TaskMessage], int],
        heartbeat_interval: float = _HEARTBEAT_INTERVAL,
        auth_ok: bool = True,
        allowed_agents: frozenset[str] | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self._bus = bus
        self._run = run
        self._heartbeat_interval = heartbeat_interval
        self._auth_ok = auth_ok
        self._allowed_agents = allowed_agents
        self._audit = audit

    def run_once(self) -> bool:
        message = self._bus.read(
            QUEUE_TASKS, visibility_timeout=_VISIBILITY_TIMEOUT
        )
        if message is None:
            return False
        if not self._auth_ok or (
            self._allowed_agents is not None
            and message.agent not in self._allowed_agents
        ):
            log = self._audit if self._audit is not None else AuditLog(ravand_home())
            log.emit(
                "worker.capability_miss",
                task_id=message.task_id,
                profile=message.profile,
                agent=message.agent,
                cwd=message.cwd_hint,
            )
            self._bus.ack(message, success=False)
            return True
        if not Path(message.cwd_hint).is_dir():
            raise FailClosed("workspace missing")
        stop = threading.Event()
        self._bus.heartbeat(message, visibility_timeout=_VISIBILITY_TIMEOUT)

        def _beat() -> None:
            while not stop.wait(self._heartbeat_interval):
                self._bus.heartbeat(
                    message, visibility_timeout=_VISIBILITY_TIMEOUT
                )

        thread = threading.Thread(target=_beat, daemon=True)
        thread.start()
        try:
            code = self._run(message)
            if code == 0:
                self._bus.archive(message)
            else:
                self._bus.ack(message, success=False)
            return True
        finally:
            stop.set()
            thread.join(timeout=1.0)
