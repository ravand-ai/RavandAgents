"""Native loop stub: no ACP spawn; session store and audit like ACP path."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ravand_audit import AuditLog
from ravand_policy import ResolvedPolicy, ravand_home
from ravand_profile import ensure_profile_home
from ravand_runtime.otel import Tracer
from ravand_runtime.run import _invoke_agent
from ravand_sessions import SessionStore

EventSink = Callable[[dict[str, Any]], None]

_STUB_MESSAGE = "native loop stub: provider plugin not configured"


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _emit(sink: EventSink, event: dict[str, Any], *, task_id: str) -> None:
    sink({"ts": _now_iso(), "taskId": task_id, **event})


def run_native_prompt(
    policy: ResolvedPolicy,
    prompt: str,
    *,
    cwd: Path,
    sink: EventSink,
    tracer: Tracer | None = None,
) -> int:
    """Run the native loop path without spawning an ACP child."""
    del prompt  # stub does not call a provider yet
    cwd = cwd.resolve()
    task_id = str(uuid.uuid4())
    root = ravand_home()
    store = SessionStore(root)
    log = AuditLog(root)
    tracer = tracer if tracer is not None else Tracer.from_env()

    ensure_profile_home(policy.home)
    log.emit(
        "agent.selected",
        task_id=task_id,
        profile=policy.profile,
        agent=policy.agent,
        cwd=str(cwd),
        detail=policy.account or None,
    )
    record = store.start(
        task_id=task_id,
        cwd=str(cwd),
        profile=policy.profile,
        agent=policy.agent,
        command=[],
        account=policy.account or None,
    )
    log.emit(
        "run.started",
        task_id=task_id,
        profile=policy.profile,
        agent=policy.agent,
        cwd=str(cwd),
    )
    _emit(sink, {"type": "run.started"}, task_id=task_id)

    status = "stub"
    with _invoke_agent(
        tracer,
        policy,
        task_id=task_id,
        conversation_id=record.id,
    ):
        _emit(
            sink,
            {"type": "text.delta", "text": _STUB_MESSAGE},
            task_id=task_id,
        )
        tracer.record_result("ok")

    store.finish(record.id, status=status)
    log.emit(
        "run.ended",
        task_id=task_id,
        profile=policy.profile,
        agent=policy.agent,
        detail=status,
    )
    _emit(sink, {"type": "run.ended", "status": status}, task_id=task_id)
    return 0
