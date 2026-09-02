"""Worker: read q.tasks, heartbeat while live, archive or ack."""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

from ravand_audit import AuditLog
from ravand_bus import TaskMessage
from ravand_policy import (
    FailClosed as PolicyFailClosed,
    PolicyDenied,
    UnknownAgent,
    ravand_home,
    resolve,
)

QUEUE_TASKS = "q.tasks"
_VISIBILITY_TIMEOUT = 600
_HEARTBEAT_INTERVAL = 30.0
DEFAULT_WORKER_INTERVAL = 1.0
_TOKEN_MARKERS = ("sk-", "xai-", "Bearer", "cookies")


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
        self._cordoned = False
        self._draining = False
        self._stopped = False
        self._busy = False
        self._idle = threading.Event()
        self._idle.set()
        self._lock = threading.Lock()

    @property
    def stopped(self) -> bool:
        with self._lock:
            return self._stopped

    def cordon(self) -> None:
        """Nack new jobs without running them."""
        self._cordoned = True

    def drain(self) -> None:
        """Finish in-flight work, then stop taking jobs."""
        with self._lock:
            self._cordoned = True
            self._draining = True
            if not self._busy:
                self._stopped = True
        self._idle.wait()
        with self._lock:
            self._stopped = True

    def _emit(self, event_type: str, message: TaskMessage) -> None:
        log = self._audit if self._audit is not None else AuditLog(ravand_home())
        log.emit(
            event_type,
            task_id=message.task_id,
            profile=message.profile,
            agent=message.agent,
            cwd=message.cwd_hint,
        )

    def run_once(self) -> bool:
        with self._lock:
            if self._stopped or self._draining:
                self._stopped = True
                return False
        message = self._bus.read(
            QUEUE_TASKS, visibility_timeout=_VISIBILITY_TIMEOUT
        )
        if message is None:
            return False
        with self._lock:
            if self._stopped or self._draining:
                self._bus.ack(message, success=False)
                self._stopped = True
                return False
            cordoned = self._cordoned
        if cordoned:
            self._emit("worker.cordoned", message)
            self._bus.ack(message, success=False)
            return True
        if not self._auth_ok or (
            self._allowed_agents is not None
            and message.agent not in self._allowed_agents
        ):
            self._emit("worker.capability_miss", message)
            self._bus.ack(message, success=False)
            return True
        if not Path(message.cwd_hint).is_dir():
            raise FailClosed("workspace missing")
        with self._lock:
            if self._stopped or self._draining:
                self._bus.ack(message, success=False)
                self._stopped = True
                return False
            self._busy = True
            self._idle.clear()
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
            with self._lock:
                self._busy = False
                if self._draining:
                    self._stopped = True
                self._idle.set()


def _scrub(text: str) -> str:
    for marker in _TOKEN_MARKERS:
        if marker in text:
            return "fail closed"
    return text


def _default_run(message: TaskMessage) -> int:
    from ravand_runtime.run import run_prompt

    cwd = Path(message.cwd_hint)
    try:
        policy = resolve(
            cwd,
            profile_override=message.profile,
            agent_override=message.agent,
        )
    except (PolicyFailClosed, PolicyDenied, UnknownAgent) as exc:
        return getattr(exc, "exit_code", 3)
    return run_prompt(
        policy,
        message.prompt,
        cwd=cwd,
        sink=lambda _event: None,
        yes=True,
    )


def serve_worker(
    *,
    bus: object | None = None,
    run: Callable[[TaskMessage], int] | None = None,
    interval: float = DEFAULT_WORKER_INTERVAL,
    sleep: Callable[[float], None] | None = None,
    max_ticks: int | None = None,
    auth_ok: bool = True,
    allowed_agents: frozenset[str] | None = None,
    audit: AuditLog | None = None,
    worker: Worker | None = None,
) -> int:
    """Loop Worker.run_once until drain/stop or max_ticks.

    Tests inject sleep and max_ticks. Default bus is in-memory. No Kafka.
    """
    if not isinstance(interval, (int, float)) or interval < 0:
        print("fail closed", file=sys.stderr)
        return 3
    if max_ticks is not None and (not isinstance(max_ticks, int) or max_ticks < 1):
        print("fail closed", file=sys.stderr)
        return 3
    sleeper = sleep if sleep is not None else time.sleep
    if worker is None:
        actual_bus = bus
        if actual_bus is None:
            from ravand_bus import Bus

            actual_bus = Bus()
        runner = run if run is not None else _default_run
        log = audit if audit is not None else AuditLog(ravand_home())
        worker = Worker(
            actual_bus,
            run=runner,
            auth_ok=auth_ok,
            allowed_agents=allowed_agents,
            audit=log,
        )
    tick = 0
    try:
        while True:
            worker.run_once()
            tick += 1
            if worker.stopped:
                return 0
            if max_ticks is not None and tick >= max_ticks:
                return 0
            sleeper(interval)
    except KeyboardInterrupt:
        return 0
    except FailClosed as exc:
        print(_scrub(str(exc)), file=sys.stderr)
        return 3
