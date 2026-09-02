"""Shared Policy-step runner for workflow and pipeline. Fail closed."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Protocol, TypeVar

from ravand_audit import AuditLog
from ravand_policy import (
    PolicyDenied,
    UnknownAgent,
    require_function,
    resolve,
)
from ravand_runtime.dispatch import dispatch
from ravand_sessions import FailClosed, SessionStore


class PolicyStep(Protocol):
    id: str
    prompt: str
    agent: str | None
    account: str | None
    functions: tuple[str, ...]
    subagents: tuple[str, ...]


T = TypeVar("T", bound=PolicyStep)


def _deny(
    *,
    root_id: str,
    step: PolicyStep | None,
    cwd: Path,
    audit: AuditLog,
    detail: str,
    profile: str | None = None,
    agent: str | None = None,
) -> None:
    task_id = root_id
    if step is not None:
        task_id = f"{root_id}:{step.id}"
    audit.emit(
        "agent.denied",
        task_id=task_id,
        profile=profile,
        agent=agent,
        cwd=str(cwd),
        detail=detail,
    )


def run_policy_steps(
    steps: Sequence[T],
    *,
    cwd: Path,
    root_id: str,
    kind: str,
    bus: object | None = None,
    store: SessionStore | None = None,
    audit: AuditLog,
    run: Callable[[T], object] | None = None,
) -> list[T]:
    """Resolve Policy for every step, then dispatch (or call ``run``).

    Plans all steps before any side effect so a mid-list deny stays fail-closed.
    ``kind`` is ``workflow`` or ``pipeline`` (dispatch error text only).
    """
    cwd = cwd.resolve()
    planned: list[tuple[T, object]] = []
    for step in steps:
        try:
            policy = resolve(
                cwd,
                agent_override=step.agent,
                account_override=step.account,
            )
        except (PolicyDenied, UnknownAgent) as exc:
            _deny(
                root_id=root_id,
                step=step,
                cwd=cwd,
                audit=audit,
                detail=str(exc),
            )
            raise
        try:
            for name in step.functions:
                require_function(policy, name)
            for name in step.subagents:
                resolve(
                    cwd,
                    agent_override=name,
                    account_override=step.account,
                )
        except (PolicyDenied, UnknownAgent) as exc:
            _deny(
                root_id=root_id,
                step=step,
                cwd=cwd,
                audit=audit,
                detail=str(exc),
                profile=policy.profile,
                agent=policy.agent,
            )
            raise
        planned.append((step, policy))
    executed: list[T] = []
    for step, _policy in planned:
        if run is not None:
            run(step)
        elif bus is not None:
            if store is None:
                raise PolicyDenied(f"{kind} dispatch requires a session store")
            try:
                dispatch(
                    cwd,
                    step.prompt,
                    bus=bus,
                    store=store,
                    task_id=f"{root_id}:{step.id}:{uuid.uuid4()}",
                    agent_override=step.agent,
                    account_override=step.account,
                )
            except FailClosed:
                _deny(
                    root_id=root_id,
                    step=step,
                    cwd=cwd,
                    audit=audit,
                    detail="dispatch failed",
                )
                raise
        executed.append(step)
    return executed
