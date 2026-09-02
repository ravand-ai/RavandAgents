"""Compose ravand serve: http + cron + worker on one Bus."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from ravand_audit import AuditLog
from ravand_bus import Bus, TaskMessage
from ravand_policy import (
    FailClosed,
    PolicyDenied,
    UnknownAgent,
    ravand_home,
    resolve,
)
from ravand_runtime.cron import DEFAULT_CRON_INTERVAL, serve_cron
from ravand_runtime.http_api import DEFAULT_HTTP_PORT, HttpApiServer, serve_http
from ravand_runtime.worker import DEFAULT_WORKER_INTERVAL, Worker, serve_worker
from ravand_sessions import SessionStore

_TOKEN_MARKERS = ("sk-", "xai-", "Bearer", "cookies")


def _scrub(text: str) -> str:
    for marker in _TOKEN_MARKERS:
        if marker in text:
            return "fail closed"
    return text


def serve_all(
    cwd: Path | None = None,
    *,
    port: int = DEFAULT_HTTP_PORT,
    bus: Bus | None = None,
    store: SessionStore | None = None,
    audit: AuditLog | None = None,
    now: datetime | None = None,
    cron_interval: float = DEFAULT_CRON_INTERVAL,
    worker_interval: float = DEFAULT_WORKER_INTERVAL,
    sleep: Callable[[float], None] | None = None,
    max_ticks: int | None = None,
    run: Callable[[TaskMessage], int] | None = None,
    on_listen: Callable[[HttpApiServer], None] | None = None,
    worker: Worker | None = None,
) -> int:
    """Start http, cron, and worker in one process on one Bus.

    Fail closed if Policy cannot resolve cwd. Tests inject bus, sleep,
    run, and on_listen. Stdlib threads. No Kafka. No TUI.
    """
    root = Path(cwd) if cwd is not None else Path.cwd()
    root = root.resolve()
    try:
        resolve(root)
    except (FailClosed, PolicyDenied, UnknownAgent) as exc:
        print(_scrub(str(exc)), file=sys.stderr)
        return getattr(exc, "exit_code", 3)
    actual_bus = bus if bus is not None else Bus()
    actual_store = store if store is not None else SessionStore(ravand_home())
    log = audit if audit is not None else AuditLog(ravand_home())
    stop = threading.Event()

    def sleeper(seconds: float) -> None:
        if sleep is not None:
            sleep(seconds)
            if stop.is_set():
                raise KeyboardInterrupt
            return
        if seconds <= 0:
            if stop.is_set():
                raise KeyboardInterrupt
            return
        if stop.wait(timeout=seconds):
            raise KeyboardInterrupt

    threads: list[threading.Thread] = []

    def run_cron() -> None:
        serve_cron(
            cwd=root,
            now=now,
            interval=cron_interval,
            bus=actual_bus,
            store=actual_store,
            audit=log,
            sleep=sleeper,
            max_ticks=max_ticks,
        )

    def run_worker() -> None:
        serve_worker(
            bus=actual_bus,
            run=run,
            interval=worker_interval,
            sleep=sleeper,
            max_ticks=max_ticks,
            audit=log,
            worker=worker,
        )

    try:
        cron_thread = threading.Thread(
            target=run_cron, name="ravand-cron", daemon=True
        )
        worker_thread = threading.Thread(
            target=run_worker, name="ravand-worker", daemon=True
        )
        cron_thread.start()
        worker_thread.start()
        threads.extend((cron_thread, worker_thread))
        return serve_http(
            port=port,
            workspace_root=root,
            bus=actual_bus,
            store=actual_store,
            on_listen=on_listen,
        )
    except KeyboardInterrupt:
        return 0
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=1.0)
