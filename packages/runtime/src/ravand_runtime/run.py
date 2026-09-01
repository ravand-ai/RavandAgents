"""Run one ACP prompt and emit SessionEvent dicts."""

from __future__ import annotations

import hashlib
import json
import os
import socket
import sys
import threading
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager, nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ravand_audit import AuditLog
from ravand_hooks import run_tool_pre
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
from ravand_memory import FailClosed as MemoryFailClosed, FileStore
from ravand_runtime.agents_md import attach_agents_md
from ravand_runtime.hooks import load_tool_pre_command
from ravand_runtime.memory import augment_prompt, load_memory_config, open_file_store
from ravand_runtime.otel import Tracer
from ravand_sessions import SessionRecord, SessionStore

EventSink = Callable[[dict[str, Any]], None]
AskFn = Callable[[str], bool]

_OVERFLOW_MARKERS = ("rate_limit", "quota", "crash")


def _policy_hash(policy: ResolvedPolicy) -> str:
    payload = json.dumps(
        {
            "agent": policy.agent,
            "classification": policy.classification,
            "deny": policy.deny,
            "overflow": policy.overflow_agent or "",
            "permissions": policy.permissions,
            "profile": policy.profile,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _otel_result(status: str, *, overflow: bool) -> str:
    if overflow:
        return "rate_limit"
    if status == "ok":
        return "ok"
    if status == "auth":
        return "auth_missing"
    if status == "cancelled":
        return "ok"
    return "crash"


@contextmanager
def _invoke_agent(
    tracer: Tracer,
    policy: ResolvedPolicy,
    *,
    task_id: str,
    conversation_id: str,
    overflow_of: str | None = None,
) -> Iterator[None]:
    with tracer.invoke_agent(
        agent=policy.agent,
        task_id=task_id,
        profile=policy.profile,
        conversation_id=conversation_id,
        policy_hash=_policy_hash(policy),
        host=socket.gethostname(),
        overflow_of=overflow_of,
    ):
        yield


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _emit(sink: EventSink, event: dict[str, Any], *, task_id: str) -> None:
    sink({"ts": _now_iso(), "taskId": task_id, **event})


def _overflow_triggered(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(marker in text for marker in _OVERFLOW_MARKERS)


def _content_blocks(content: Any) -> list[dict[str, Any]]:
    if isinstance(content, dict):
        return [content]
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    return []


def _short_label(update: dict[str, Any]) -> str:
    raw = (
        update.get("title")
        or update.get("kind")
        or update.get("toolCallId")
        or "tool"
    )
    label = " ".join(str(raw).split())
    if len(label) > 80:
        label = label[:77] + "..."
    return label


def _emit_session_update(
    sink: EventSink,
    update: dict[str, Any],
    *,
    task_id: str,
    tracer: Tracer | None = None,
) -> None:
    kind = str(update.get("sessionUpdate") or "").lower()
    blocks = _content_blocks(update.get("content"))
    texts = [str(b["text"]) for b in blocks if b.get("text")]
    if "thought" in kind or "think" in kind:
        for text in texts:
            _emit(sink, {"type": "thinking.delta", "text": text}, task_id=task_id)
        return
    if "tool_call" in kind:
        label = _short_label(update)
        status = str(update.get("status") or "")
        done = "update" in kind or status in {"completed", "failed"}
        event_type = (
            "tool.result" if done and status != "in_progress" else "tool.call"
        )
        span = (
            tracer.execute_tool(name=label)
            if tracer is not None and event_type == "tool.call"
            else nullcontext()
        )
        with span:
            _emit(
                sink,
                {
                    "type": event_type,
                    "tool": label,
                    "status": status or ("completed" if done else "in_progress"),
                },
                task_id=task_id,
            )
        return
    for text in texts:
        _emit(sink, {"type": "text.delta", "text": text}, task_id=task_id)


def pick_option_id(options: list[Any], decision: str) -> str:
    """Map a broker decision to an advertised ACP permission optionId."""
    opts = [o for o in options if isinstance(o, dict) and o.get("optionId")]
    if decision == "allow":
        for kind in ("allow_once", "allow_always"):
            for opt in opts:
                if str(opt.get("kind") or "").lower() == kind:
                    return str(opt["optionId"])
        for opt in opts:
            oid = str(opt["optionId"]).lower()
            if "allow" in oid:
                return str(opt["optionId"])
    else:
        for kind in ("reject_once", "reject_always"):
            for opt in opts:
                if str(opt.get("kind") or "").lower() == kind:
                    return str(opt["optionId"])
        for opt in opts:
            oid = str(opt["optionId"]).lower()
            if "reject" in oid or "deny" in oid:
                return str(opt["optionId"])
    for opt in opts:
        kind = str(opt.get("kind") or "").lower()
        oid = str(opt["optionId"]).lower()
        if kind.startswith("reject") or "reject" in oid or "deny" in oid:
            return str(opt["optionId"])
    raise AcpError(f"no permission option for decision {decision!r}")


def _watch_cancel(client: AcpClient, cancel: threading.Event) -> None:
    def _run() -> None:
        cancel.wait()
        client.close()

    threading.Thread(target=_run, daemon=True).start()


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
    tracer: Tracer,
    ask: AskFn | None = None,
    yes: bool = False,
    cancel: threading.Event | None = None,
    overflow_of: str | None = None,
) -> tuple[int, str, str | None, bool]:
    session_acp_id: str | None = None
    status = "error"
    exit_code = 5
    overflow = False
    spanned = False
    if cancel is not None:
        _watch_cancel(client, cancel)
        if cancel.is_set():
            status = "cancelled"
            return 0, status, None, False
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
            params = msg.get("params") or {}
            update = params.get("update") if isinstance(params, dict) else None
            if not isinstance(update, dict):
                return
            _emit_session_update(sink, update, task_id=task_id, tracer=tracer)

        def on_permission(msg: dict[str, Any]) -> dict[str, Any]:
            params = msg.get("params") or {}
            if not isinstance(params, dict):
                params = {}
            tool = params.get("toolCall") or {}
            if not isinstance(tool, dict):
                tool = {}
            detail = str(tool.get("title") or tool.get("kind") or "tool")
            hook_command = load_tool_pre_command(cwd)
            if hook_command is not None:
                hook_decision = run_tool_pre(
                    hook_command,
                    cwd,
                    os.environ,
                )
                if hook_decision == "deny":
                    log.emit(
                        "hook.deny",
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
                    options = params.get("options") or []
                    if not isinstance(options, list):
                        options = []
                    option_id = pick_option_id(options, "deny")
                    return {
                        "outcome": {
                            "outcome": "selected",
                            "optionId": option_id,
                        }
                    }
            decision = decide_repo_only(tool, str(cwd))
            if decision != "deny" and not yes and ask is not None:
                if not ask(detail):
                    decision = "deny"
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

        with _invoke_agent(
            tracer,
            policy,
            task_id=task_id,
            conversation_id=str(session_acp_id or ""),
            overflow_of=overflow_of,
        ):
            spanned = True
            try:
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
                    client.request_with_handlers(
                        "session/close", {"sessionId": session_acp_id}
                    )
                except Exception:
                    pass
                status = "ok"
                exit_code = 0
                tracer.record_result("ok")
            except AuthRequired:
                tracer.record_result("auth_missing")
                raise
            except Exception as inner:
                if cancel is not None and cancel.is_set():
                    tracer.record_result("ok")
                elif _overflow_triggered(inner):
                    tracer.record_result("rate_limit")
                else:
                    tracer.record_result("crash")
                raise
    except AuthRequired:
        status = "auth"
        exit_code = _auth_missing(policy, task_id=task_id, log=log)
        if not spanned:
            with _invoke_agent(
                tracer, policy, task_id=task_id, conversation_id=""
            ):
                tracer.record_result("auth_missing")
    except Exception as exc:
        if cancel is not None and cancel.is_set():
            status = "cancelled"
            exit_code = 0
            overflow = False
        else:
            overflow = _overflow_triggered(exc)
            print(str(exc), file=sys.stderr)
            if not spanned:
                with _invoke_agent(
                    tracer,
                    policy,
                    task_id=task_id,
                    conversation_id=str(session_acp_id or ""),
                    overflow_of=overflow_of,
                ):
                    tracer.record_result(_otel_result(status, overflow=overflow))
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


def _memory_for_run(
    policy: ResolvedPolicy,
    prompt: str,
    *,
    cwd: Path,
    task_id: str,
) -> tuple[str, FileStore | None]:
    """Return augmented prompt and optional FileStore when [memory] is configured."""
    config = load_memory_config(cwd)
    if config is None:
        return prompt, None
    store = open_file_store(
        config,
        policy,
        root=ravand_home(),
        cwd=cwd,
        task_id=task_id,
    )
    notes = store.read()
    return augment_prompt(prompt, notes), store


def run_prompt(
    policy: ResolvedPolicy,
    prompt: str,
    *,
    cwd: Path,
    sink: EventSink,
    ask: AskFn | None = None,
    yes: bool = False,
    cancel: threading.Event | None = None,
    tracer: Tracer | None = None,
) -> int:
    cwd = cwd.resolve()
    task_id = str(uuid.uuid4())
    root = ravand_home()
    store = SessionStore(root)
    log = AuditLog(root)
    tracer = tracer if tracer is not None else Tracer.from_env()

    try:
        agent_prompt, memory_store = _memory_for_run(
            policy, prompt, cwd=cwd, task_id=task_id
        )
    except MemoryFailClosed as exc:
        print(str(exc), file=sys.stderr)
        return 3
    agent_prompt = attach_agents_md(policy, agent_prompt, cwd)

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
        with _invoke_agent(tracer, policy, task_id=task_id, conversation_id=""):
            tracer.record_result("auth_missing")
        return _auth_missing(policy, task_id=task_id, log=log)
    except Exception as exc:
        with _invoke_agent(tracer, policy, task_id=task_id, conversation_id=""):
            tracer.record_result("crash")
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

    exit_code, status, _, triggered = _attempt_run(
        client,
        policy,
        agent_prompt,
        cwd=cwd,
        sink=sink,
        task_id=task_id,
        store=store,
        log=log,
        record=record,
        tracer=tracer,
        ask=ask,
        yes=yes,
        cancel=cancel,
    )
    if status == "ok" and memory_store is not None:
        memory_store.write(prompt)
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
        with _invoke_agent(
            tracer,
            overflow_policy,
            task_id=task_id,
            conversation_id="",
            overflow_of=record.id,
        ):
            tracer.record_result("auth_missing")
        return _auth_missing(overflow_policy, task_id=task_id, log=log)
    except Exception as exc:
        with _invoke_agent(
            tracer,
            overflow_policy,
            task_id=task_id,
            conversation_id="",
            overflow_of=record.id,
        ):
            tracer.record_result("crash")
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
        tracer=tracer,
        ask=ask,
        yes=yes,
        cancel=cancel,
        overflow_of=record.id,
    )
    return overflow_exit
