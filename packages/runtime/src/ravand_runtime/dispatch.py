"""Dispatcher: after policy resolve, Bus.send TaskMessage to q.tasks."""

from __future__ import annotations

from pathlib import Path

from ravand_bus import Bus, TaskMessage
from ravand_policy import resolve
from ravand_sessions import SessionRecord, SessionStore


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
) -> SessionRecord:
    cwd = cwd.resolve()
    policy = resolve(
        cwd,
        profile_override=profile_override,
        agent_override=agent_override,
        account_override=account_override,
    )
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
    bus.send("q.tasks", message)
    return record
