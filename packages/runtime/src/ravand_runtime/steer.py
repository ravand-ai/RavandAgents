"""Steer: send session/prompt on an existing ACP session."""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ravand_audit import AuditLog
from ravand_permissions import decide_repo_only
from ravand_policy import PolicyDenied, UnknownAgent, ravand_home, resolve
from ravand_profile import ensure_profile_home
from ravand_runtime.acp import AcpClient, AcpError, AuthRequired, spawn
from ravand_runtime.run import (
    _auth_missing,
    _connect,
    _emit,
    _emit_session_update,
    pick_option_id,
)
from ravand_runtime.otel import Tracer
from ravand_sessions import SessionStore

EventSink = Callable[[dict[str, Any]], None]


def _load_session(store: SessionStore, session_id: str) -> tuple[Any, int]:
    try:
        record = store.load(session_id)
    except FileNotFoundError:
        print(f"unknown session: {session_id!r}", file=sys.stderr)
        return None, 5
    if not record.acp_session_id:
        print(f"session {session_id!r} has no acp session id", file=sys.stderr)
        return None, 5
    return record, 0


def steer_prompt(
    session_id: str,
    text: str,
    *,
    sink: EventSink,
    tracer: Tracer | None = None,
) -> int:
    root = ravand_home()
    store = SessionStore(root)
    record, err = _load_session(store, session_id)
    if record is None:
        return err

    cwd = Path(record.cwd)
    try:
        policy = resolve(cwd, agent_override=record.agent)
    except (PolicyDenied, UnknownAgent) as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code

    if policy.agent in policy.deny:
        denied = PolicyDenied(f"agent {policy.agent!r} is denied")
        print(str(denied), file=sys.stderr)
        return denied.exit_code

    task_id = record.task_id
    log = AuditLog(root)
    tracer = tracer if tracer is not None else Tracer.from_env()

    ensure_profile_home(policy.home)
    try:
        client = _connect(policy, cwd=cwd)
    except AuthRequired:
        return _auth_missing(policy, task_id=task_id, log=log)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 5

    acp_session_id = record.acp_session_id
    assert acp_session_id is not None

    try:
        loaded = client.request_with_handlers(
            "session/load",
            {"sessionId": acp_session_id},
        )
        acp_session_id = str(loaded.get("sessionId") or acp_session_id)
    except AcpError as exc:
        print(str(exc), file=sys.stderr)
        client.close()
        return 5

    log.emit(
        "steer.accepted",
        task_id=task_id,
        profile=record.profile,
        agent=record.agent,
    )
    _emit(sink, {"type": "steer.accepted"}, task_id=task_id)

    def on_update(msg: dict[str, Any]) -> None:
        params = msg.get("params") or {}
        update = params.get("update") if isinstance(params, dict) else None
        if isinstance(update, dict):
            _emit_session_update(sink, update, task_id=task_id, tracer=tracer)

    def on_permission(msg: dict[str, Any]) -> dict[str, Any]:
        params = msg.get("params") or {}
        if not isinstance(params, dict):
            params = {}
        tool = params.get("toolCall") or {}
        if not isinstance(tool, dict):
            tool = {}
        decision = decide_repo_only(tool, str(cwd))
        audit_type = "permission.deny" if decision == "deny" else "permission.allow"
        log.emit(
            audit_type,
            task_id=task_id,
            profile=record.profile,
            agent=record.agent,
            detail=str(tool.get("title") or tool.get("kind") or "tool"),
        )
        options = params.get("options") or []
        if not isinstance(options, list):
            options = []
        option_id = pick_option_id(options, decision)
        return {
            "outcome": {
                "outcome": "selected",
                "optionId": option_id,
            }
        }

    status = "error"
    exit_code = 5
    try:
        client.request_with_handlers(
            "session/prompt",
            {
                "sessionId": acp_session_id,
                "prompt": [{"type": "text", "text": text}],
            },
            on_update=on_update,
            on_permission=on_permission,
        )
        try:
            client.request_with_handlers(
                "session/close", {"sessionId": acp_session_id}
            )
        except Exception:
            pass
        status = "ok"
        exit_code = 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
    finally:
        client.close()
        _emit(sink, {"type": "run.ended", "status": status}, task_id=task_id)

    return exit_code
