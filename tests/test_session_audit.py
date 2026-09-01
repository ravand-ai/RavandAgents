"""Slice 3 TDD: session store and append-only audit log."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from ravand_audit import AuditLog
from ravand_sessions import SessionRecord, SessionStore

FORBIDDEN = ("sk-", "xai-", "Bearer", "cookies")


def _ravand_root(home: Path) -> Path:
    return home


@pytest.fixture
def ravand_home(tmp_path: Path) -> Path:
    root = tmp_path / "ravand"
    root.mkdir()
    return root


def test_session_file_written_under_ravand_home(ravand_home: Path) -> None:
    store = SessionStore(ravand_home)
    record = store.start(
        task_id="task-1",
        cwd="/repo",
        profile="work",
        agent="grok",
        command=["grok", "agent", "stdio"],
    )
    path = ravand_home / "sessions" / f"{record.id}.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["id"] == record.id
    assert data["taskId"] == "task-1"
    assert data["profile"] == "work"
    assert data["agent"] == "grok"
    assert data["status"] == "running"
    assert data["command"] == ["grok", "agent", "stdio"]


def test_session_finish_updates_status_and_ended_at(ravand_home: Path) -> None:
    store = SessionStore(ravand_home)
    record = store.start(
        task_id="task-2",
        cwd="/repo",
        profile="work",
        agent="grok",
        command=["grok", "agent", "stdio"],
    )
    finished = store.finish(record.id, status="ok", acp_session_id="acp-99")
    assert finished.status == "ok"
    assert finished.ended_at is not None
    assert finished.acp_session_id == "acp-99"
    reloaded = store.load(record.id)
    assert reloaded.status == "ok"


def test_audit_append_writes_jsonl_lines(ravand_home: Path) -> None:
    log = AuditLog(ravand_home)
    log.emit(
        "run.started",
        task_id="task-1",
        profile="work",
        agent="grok",
        cwd="/repo",
    )
    log.emit("run.ended", task_id="task-1", profile="work", agent="grok", detail="ok")
    lines = (ravand_home / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    first = json.loads(lines[0])
    assert first["type"] == "run.started"
    assert first["taskId"] == "task-1"
    assert "ts" in first


def test_audit_agent_denied_without_spawn(ravand_home: Path) -> None:
    log = AuditLog(ravand_home)
    log.emit(
        "agent.denied",
        task_id="task-deny",
        profile="personal",
        agent="grok",
        detail="customer classification cannot use personal profile",
    )
    event = json.loads((ravand_home / "audit.jsonl").read_text(encoding="utf-8"))
    assert event["type"] == "agent.denied"
    assert "sessions" not in list(ravand_home.glob("sessions/*.json"))


def test_audit_permission_allow_and_deny(ravand_home: Path) -> None:
    log = AuditLog(ravand_home)
    log.emit(
        "permission.allow",
        task_id="t",
        profile="work",
        agent="grok",
        detail="read README.md",
    )
    log.emit(
        "permission.deny",
        task_id="t",
        profile="work",
        agent="grok",
        detail="write /etc/passwd",
    )
    types = [
        json.loads(line)["type"]
        for line in (ravand_home / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert types == ["permission.allow", "permission.deny"]


def test_work_profile_omits_prompt_body_unless_audit_bodies(
    ravand_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("RAVAND_AUDIT_BODIES", raising=False)
    log = AuditLog(ravand_home)
    secret_prompt = "implement feature with sk-secret-token"
    log.emit(
        "run.started",
        task_id="t",
        profile="work",
        agent="grok",
        detail=secret_prompt,
    )
    event = json.loads((ravand_home / "audit.jsonl").read_text(encoding="utf-8"))
    assert secret_prompt not in event.get("detail", "")
    assert event.get("detail") in (None, "", "[redacted]")

    log2 = AuditLog(ravand_home)
    monkeypatch.setenv("RAVAND_AUDIT_BODIES", "1")
    log2.emit(
        "run.started",
        task_id="t2",
        profile="work",
        agent="grok",
        detail=secret_prompt,
    )
    lines = (ravand_home / "audit.jsonl").read_text(encoding="utf-8").strip().splitlines()
    with_bodies = json.loads(lines[-1])
    assert with_bodies["detail"] == secret_prompt


def test_session_and_audit_contain_no_secrets(ravand_home: Path) -> None:
    store = SessionStore(ravand_home)
    log = AuditLog(ravand_home)
    record = store.start(
        task_id="job-42",
        cwd="/repo",
        profile="work",
        agent="grok",
        command=["grok", "agent", "stdio"],
    )
    store.finish(record.id, status="ok")
    log.emit(
        "agent.selected",
        task_id="job-42",
        profile="work",
        agent="grok",
        cwd="/repo",
    )
    log.emit("run.started", task_id="job-42", profile="work", agent="grok")
    log.emit("run.ended", task_id="job-42", profile="work", agent="grok")
    blob = (ravand_home / "sessions" / f"{record.id}.json").read_text(encoding="utf-8")
    blob += (ravand_home / "audit.jsonl").read_text(encoding="utf-8")
    for marker in FORBIDDEN:
        assert marker not in blob


def test_successful_run_flow_produces_session_and_audit_lines(ravand_home: Path) -> None:
    """Simulate a successful run lifecycle using session + audit packages."""
    store = SessionStore(ravand_home)
    log = AuditLog(ravand_home)
    task_id = "run-ok-1"
    log.emit(
        "agent.selected",
        task_id=task_id,
        profile="work",
        agent="grok",
        cwd=str(Path.cwd()),
    )
    record = store.start(
        task_id=task_id,
        cwd=str(Path.cwd()),
        profile="work",
        agent="grok",
        command=["grok", "agent", "stdio"],
    )
    log.emit("run.started", task_id=task_id, profile="work", agent="grok")
    store.finish(record.id, status="ok", acp_session_id="sess-1")
    log.emit("run.ended", task_id=task_id, profile="work", agent="grok", detail="ok")
    assert list((ravand_home / "sessions").glob("*.json"))
    audit_types = [
        json.loads(line)["type"]
        for line in (ravand_home / "audit.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert "agent.selected" in audit_types
    assert "run.started" in audit_types
    assert "run.ended" in audit_types


def test_auth_missing_audit_event(ravand_home: Path) -> None:
    log = AuditLog(ravand_home)
    log.emit(
        "auth.missing",
        task_id="auth-1",
        profile="work",
        agent="grok",
        detail="grok login",
    )
    event = json.loads((ravand_home / "audit.jsonl").read_text(encoding="utf-8"))
    assert event["type"] == "auth.missing"
