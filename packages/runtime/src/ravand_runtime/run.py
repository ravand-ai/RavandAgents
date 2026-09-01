"""Run one ACP prompt and emit SessionEvent dicts."""

from __future__ import annotations

import json
import sys
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ravand_audit import AuditLog
from ravand_permissions import decide_repo_only
from ravand_policy import ResolvedPolicy, ravand_home, resolve
from ravand_profile import ensure_profile_home
from ravand_registry import login_hint
from ravand_runtime.acp import (
    AcpClient,
    AcpError,
    AuthRequired,
    ensure_authenticated,
    is_auth_error,
    spawn,
)
from ravand_sessions import SessionRecord, SessionStore

EventSink = Callable[[dict[str, Any]], None]

_OVERFLOW_MARKERS = ("rate_limit", "quota", "crash")


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _emit(sink: EventSink, event: dict[str, Any], *, task_id: str) -> None:
    sink({"ts": _now_iso(), "taskId": task_id, **event})


def _overflow_triggered(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _OVERFLOW_MARKERS)


def _should_overflow(policy: ResolvedPolicy, *, triggered: bool) -> bool:
    overflow = policy.overflow_agent
    if not triggered or not overflow:
        return False
    return overflow not in policy.deny


def audit_agent_denied(detail: str, *, cwd: Path | None = None) -> None:
    """Record a policy denial without spawning an agent."""
    task_id = str(uuid.uuid4())
    log = AuditLog(ravand_home())
    log.emit(
        "agent.denied",
        task_id=task_id,
        cwd=str(cwd.resolve()) if cwd else None,
        detail=detail,
    )


def _connect(policy: ResolvedPolicy, *, cwd: Path) -> AcpClient:
    """Spawn, initialize, and authenticate. Fails closed on auth."""
    client = spawn(policy.command, cwd=cwd, home=policy.home)
    try:
        init = client.request_with_handlers("initialize", {"protocolVersion": 1})
        ensure_authenticated(client, init, agent=policy.agent)
    except Exception:
        client.close()
        raise
    return client


def _auth_missing(
    policy: ResolvedPolicy,
    *,
    task_id: str,
    log: AuditLog,
) -> int:
    """Audit auth.missing, print the vendor login hint, exit 2."""
    hint = login_hint(policy.agent)
    print(
        f"agent {policy.agent!r} requires login. "
        f"Run: ravand login {policy.profile} / {hint}",
        file=sys.stderr,
    )
    log.emit(
        "auth.missing",
        task_id=task_id,
        profile=policy.profile,
        agent=policy.agent,
        detail=f"ravand login {policy.profile} / {hint}",
    )
    return 2


def _attempt_run(
    client: AcpClient,
    policy: ResolvedPolicy,
    prompt: str,
    *,
    cwd: Path,
    sink: EventSink,
    task_id: str,
    store: SessionStore,
    log: AuditLog,
    record: SessionRecord,
) -> tuple[int, str, str | None, bool]:
    session_acp_id: str | None = None
    status = "error"
    exit_code = 5
    overflow = False
    try:
        try:
            session = client.request_with_handlers(
                "session/new",
                {"cwd": str(cwd), "mcpServers": []},
            )
        except AcpError as exc:
            if is_auth_error(exc):
                raise AuthRequired(policy.agent) from exc
            raise
        session_acp_id = session.get("sessionId")

        def on_update(msg: dict[str, Any]) -> None:
            update = (msg.get("params") or {}).get("update") or {}
            content = update.get("content") or {}
            text = content.get("text")
            if text:
                _emit(sink, {"type": "text.delta", "text": text}, task_id=task_id)

        def on_permission(msg: dict[str, Any]) -> dict[str, Any]:
            params = msg.get("params") or {}
            tool = params.get("toolCall") or {}
            decision = decide_repo_only(tool, str(cwd))
            detail = str(tool.get("title") or tool.get("kind") or "tool")
            audit_type = "permission.deny" if decision == "deny" else "permission.allow"
            log.emit(
                audit_type,
                task_id=task_id,
                profile=policy.profile,
                agent=policy.agent,
                detail=detail,
            )
            _emit(
                sink,
                {
                    "type": "permission.ask",
                    "tool": tool.get("title") or tool.get("kind"),
                    "text": json.dumps(tool.get("rawInput") or {}),
                },
                task_id=task_id,
            )
            option = "deny" if decision == "deny" else "allow"
            return {
                "outcome": {
                    "outcome": "selected",
                    "optionId": option,
                }
            }

        client.request_with_handlers(
            "session/prompt",
            {
                "sessionId": session_acp_id,
                "prompt": [{"type": "text", "text": prompt}],
            },
            on_update=on_update,
            on_permission=on_permission,
        )
        try:
            client.request_with_handlers("session/close", {"sessionId": session_acp_id})
        except Exception:
            pass
        status = "ok"
        exit_code = 0
    except AuthRequired:
        status = "auth"
        exit_code = _auth_missing(policy, task_id=task_id, log=log)
    except Exception as exc:
        overflow = _overflow_triggered(exc)
        print(str(exc), file=sys.stderr)
    finally:
        client.close()
        store.finish(
            record.id,
            status=status,
            acp_session_id=session_acp_id if status == "ok" else None,
        )
        log.emit(
            "run.ended",
            task_id=task_id,
            profile=policy.profile,
            agent=policy.agent,
            detail=status,
        )
        _emit(sink, {"type": "run.ended", "status": status}, task_id=task_id)
    return exit_code, status, session_acp_id, overflow


def run_prompt(
    policy: ResolvedPolicy,
    prompt: str,
    *,
    cwd: Path,
    sink: EventSink,
) -> int:
    cwd = cwd.resolve()
    task_id = str(uuid.uuid4())
    root = ravand_home()
    store = SessionStore(root)
    log = AuditLog(root)

    ensure_profile_home(policy.home)
    log.emit(
        "agent.selected",
        task_id=task_id,
        profile=policy.profile,
        agent=policy.agent,
        cwd=str(cwd),
    )
    try:
        client = _connect(policy, cwd=cwd)
    except AuthRequired:
        return _auth_missing(policy, task_id=task_id, log=log)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        log.emit(
            "run.ended",
            task_id=task_id,
            profile=policy.profile,
            agent=policy.agent,
            detail="error",
        )
        _emit(sink, {"type": "run.ended", "status": "error"}, task_id=task_id)
        return 5
    record = store.start(
        task_id=task_id,
        cwd=str(cwd),
        profile=policy.profile,
        agent=policy.agent,
        command=policy.command,
    )
    log.emit(
        "run.started",
        task_id=task_id,
        profile=policy.profile,
        agent=policy.agent,
        cwd=str(cwd),
    )
    _emit(sink, {"type": "run.started"}, task_id=task_id)

    exit_code, _, _, triggered = _attempt_run(
        client,
        policy,
        prompt,
        cwd=cwd,
        sink=sink,
        task_id=task_id,
        store=store,
        log=log,
        record=record,
    )
    if not _should_overflow(policy, triggered=triggered):
        return exit_code

    overflow_agent = policy.overflow_agent
    assert overflow_agent is not None
    log.emit(
        "agent.overflow",
        task_id=task_id,
        profile=policy.profile,
        agent=policy.agent,
        detail=overflow_agent,
    )
    overflow_policy = resolve(cwd, agent_override=overflow_agent)
    ensure_profile_home(overflow_policy.home)
    log.emit(
        "agent.selected",
        task_id=task_id,
        profile=overflow_policy.profile,
        agent=overflow_policy.agent,
        cwd=str(cwd),
    )
    try:
        overflow_client = _connect(overflow_policy, cwd=cwd)
    except AuthRequired:
        return _auth_missing(overflow_policy, task_id=task_id, log=log)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        log.emit(
            "run.ended",
            task_id=task_id,
            profile=overflow_policy.profile,
            agent=overflow_policy.agent,
            detail="error",
        )
        _emit(sink, {"type": "run.ended", "status": "error"}, task_id=task_id)
        return 5
    overflow_record = store.start(
        task_id=task_id,
        cwd=str(cwd),
        profile=overflow_policy.profile,
        agent=overflow_policy.agent,
        command=overflow_policy.command,
        overflow_of=record.id,
    )
    log.emit(
        "run.started",
        task_id=task_id,
        profile=overflow_policy.profile,
        agent=overflow_policy.agent,
        cwd=str(cwd),
    )
    _emit(sink, {"type": "run.started"}, task_id=task_id)
    overflow_exit, _, _, _ = _attempt_run(
        overflow_client,
        overflow_policy,
        prompt,
        cwd=cwd,
        sink=sink,
        task_id=task_id,
        store=store,
        log=log,
        record=overflow_record,
    )
    return overflow_exit
