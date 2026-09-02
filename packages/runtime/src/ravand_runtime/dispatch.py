"""Dispatcher: after policy resolve, Bus.send TaskMessage to q.tasks."""

from __future__ import annotations

from pathlib import Path

from ravand_audit import AuditLog
from ravand_bus import Bus, FailClosed as BusFailClosed
from ravand_bus import TaskMessage
from ravand_policy import FailClosed, ravand_home, resolve
from ravand_sessions import SessionRecord, SessionStore


def _audit_denied(
    detail: str,
    *,
    task_id: str,
    cwd: Path,
    audit: AuditLog | None,
) -> None:
    log = audit if audit is not None else AuditLog(ravand_home())
    try:
        log.emit(
            "agent.denied",
            task_id=task_id,
            cwd=str(cwd),
            detail=detail,
        )
    except OSError:
        # Audit best-effort when the store itself is down.
        pass


def dispatch(
    cwd: Path,
    prompt: str,
    *,
    bus: Bus,
    store: SessionStore,
    task_id: str,
    profile_override: str | None = None,
    agent_override: str | None = None,
    account_override: str | None = None,
    audit: AuditLog | None = None,
) -> SessionRecord:
    cwd = cwd.resolve()
    try:
        policy = resolve(
            cwd,
            profile_override=profile_override,
            agent_override=agent_override,
            account_override=account_override,
        )
    except FailClosed as exc:
        _audit_denied(str(exc), task_id=task_id, cwd=cwd, audit=audit)
        raise
    try:
        bus.require_reachable()
    except BusFailClosed as exc:
        _audit_denied(str(exc), task_id=task_id, cwd=cwd, audit=audit)
        raise
    message = TaskMessage(
        task_id=task_id,
        cwd_hint=str(cwd),
        profile=policy.profile,
        agent=policy.agent,
        prompt=prompt,
        permissions=policy.permissions,
        overflow=policy.overflow_agent,
    )
    record = store.start(
        task_id=task_id,
        cwd=str(cwd),
        profile=policy.profile,
        agent=policy.agent,
        command=policy.command,
        account=policy.account or None,
    )
    try:
        bus.send("q.tasks", message)
    except BusFailClosed as exc:
        _audit_denied(str(exc), task_id=task_id, cwd=cwd, audit=audit)
        raise
    return record
