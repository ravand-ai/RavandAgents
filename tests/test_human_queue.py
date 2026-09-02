"""Human verification queue: named approver, timeout deny (GitHub issue #141).

Source of law: docs/HLD.md Permission Broker, docs/MODULAR.md Human verification,
docs/SCHEMA.md plan.deny / permission.deny. Same fail-closed path as TTY ask.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ravand_audit import AuditLog
from ravand_policy import FailClosed
from ravand_runtime.human_queue import HumanQueue

FORBIDDEN = ("sk-", "xai-", "Bearer", "cookies")


class _Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def _queue(root: Path, clock: _Clock | None = None) -> HumanQueue:
    return HumanQueue(
        root,
        monotonic=clock if clock is not None else _Clock(),
        audit=AuditLog(root),
    )


def _audit_types(root: Path) -> list[str]:
    path = root / "audit.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)["type"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _files_under(root: Path) -> list[Path]:
    return [path for path in root.rglob("*") if path.is_file()]


def test_named_approver_allows_permission(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    item = queue.enqueue(
        kind="permission",
        task_id="task-allow",
        detail="read README.md",
        approver="alice",
        timeout_sec=30,
        profile="work",
        agent="grok",
    )
    assert queue.decide(item.id, actor="alice", allow=True) is True
    assert queue.wait(item.id) is True
    assert "permission.allow" in _audit_types(tmp_path)
    assert "permission.deny" not in _audit_types(tmp_path)


def test_named_approver_mismatch_cannot_allow(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    item = queue.enqueue(
        kind="permission",
        task_id="task-mismatch",
        detail="write src/app.py",
        approver="alice",
        timeout_sec=30,
        profile="work",
        agent="grok",
    )
    with pytest.raises(FailClosed):
        queue.decide(item.id, actor="bob", allow=True)
    with pytest.raises(FailClosed):
        queue.wait(item.id)
    assert "permission.allow" not in _audit_types(tmp_path)


def test_timeout_denies_permission_and_audits(tmp_path: Path) -> None:
    clock = _Clock()
    queue = _queue(tmp_path, clock)
    item = queue.enqueue(
        kind="permission",
        task_id="task-timeout",
        detail="shell ls",
        approver="alice",
        timeout_sec=10,
        profile="work",
        agent="grok",
    )
    clock.value = 10.0
    assert queue.wait(item.id) is False
    assert "permission.deny" in _audit_types(tmp_path)
    assert "permission.allow" not in _audit_types(tmp_path)
    assert queue.decide(item.id, actor="alice", allow=True) is False


def test_timeout_denies_plan_and_audits(tmp_path: Path) -> None:
    clock = _Clock()
    queue = _queue(tmp_path, clock)
    item = queue.enqueue(
        kind="plan",
        task_id="task-plan-timeout",
        detail="edit files then test",
        approver="alice",
        timeout_sec=5,
        profile="work",
        agent="grok",
    )
    clock.value = 5.0
    assert queue.wait(item.id) is False
    assert "plan.deny" in _audit_types(tmp_path)
    assert "plan.allow" not in _audit_types(tmp_path)


def test_named_approver_denies_plan(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    item = queue.enqueue(
        kind="plan",
        task_id="task-plan-deny",
        detail="write /etc/passwd",
        approver="alice",
        timeout_sec=30,
        profile="work",
        agent="grok",
    )
    assert queue.decide(item.id, actor="alice", allow=False) is False
    assert queue.wait(item.id) is False
    assert "plan.deny" in _audit_types(tmp_path)
    assert "plan.allow" not in _audit_types(tmp_path)


def test_ask_permission_timeout_zero_denies(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    allowed = queue.ask_permission(
        "fetch https://example.com",
        task_id="task-ask",
        approver="alice",
        timeout_sec=0,
        profile="work",
        agent="grok",
    )
    assert allowed is False
    assert "permission.deny" in _audit_types(tmp_path)


def test_ask_plan_timeout_zero_denies(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    allowed = queue.ask_plan(
        "write src/app.py",
        task_id="task-ask-plan",
        approver="alice",
        timeout_sec=0,
        profile="work",
        agent="grok",
    )
    assert allowed is False
    assert "plan.deny" in _audit_types(tmp_path)


def test_queue_files_live_under_isolated_home(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    item = queue.enqueue(
        kind="permission",
        task_id="task-home",
        detail="read LICENSE",
        approver="alice",
        timeout_sec=30,
        profile="work",
        agent="grok",
    )
    path = tmp_path / "human-queue" / f"{item.id}.json"
    assert path.is_file()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["taskId"] == "task-home"
    assert data["approver"] == "alice"
    assert data["kind"] == "permission"
    assert data["status"] == "pending"


def test_missing_approver_fails_closed(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    with pytest.raises(FailClosed):
        queue.enqueue(
            kind="permission",
            task_id="task-no-approver",
            detail="read README.md",
            approver="",
            timeout_sec=30,
            profile="work",
            agent="grok",
        )
    assert _audit_types(tmp_path) == []


def test_unknown_kind_fails_closed(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    with pytest.raises(FailClosed):
        queue.enqueue(
            kind="maybe",
            task_id="task-kind",
            detail="read README.md",
            approver="alice",
            timeout_sec=30,
            profile="work",
            agent="grok",
        )


def test_refuses_secrets_in_detail(tmp_path: Path) -> None:
    queue = _queue(tmp_path)
    with pytest.raises(FailClosed):
        queue.enqueue(
            kind="permission",
            task_id="task-secret",
            detail="use sk-secret-token",
            approver="alice",
            timeout_sec=30,
            profile="work",
            agent="grok",
        )
    with pytest.raises(FailClosed):
        queue.enqueue(
            kind="plan",
            task_id="task-cookie",
            detail="see ~/.grok/cookies",
            approver="alice",
            timeout_sec=30,
            profile="work",
            agent="grok",
        )
    for path in _files_under(tmp_path):
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN:
            assert marker not in text, f"{path} leaked {marker!r}"
        assert "sk-" not in text
