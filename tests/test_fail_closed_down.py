"""Fail closed if Policy or bus/DB is down (GitHub issue #144).

Soft-deny is forbidden. When the policy store or bus cannot be reached:
FailClosed, no run/spawn, audit if possible. Down fakes only — no live DB.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ravand_audit import AuditLog
from ravand_bus import Bus, FailClosed as BusFailClosed, TaskMessage
from ravand_policy import FailClosed, resolve
from ravand_policy.store import DownPolicyStore, FilePolicyStore
from ravand_runtime.dispatch import dispatch
from ravand_runtime.run import audit_agent_denied, run_prompt
from ravand_sessions import SessionStore

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "support" / "fake_acp_agent.py"
QUEUE_TASKS = "q.tasks"


class DownBus:
    """Bus seam fake that is always unreachable."""

    def require_reachable(self) -> None:
        raise BusFailClosed("bus unreachable")

    def send(self, queue: str, message: TaskMessage) -> None:
        raise BusFailClosed("bus unreachable")

    def read(
        self, queue: str, *, visibility_timeout: float = 600
    ) -> TaskMessage | None:
        raise BusFailClosed("bus unreachable")

    def heartbeat(
        self, message: TaskMessage, *, visibility_timeout: float = 600
    ) -> None:
        raise BusFailClosed("bus unreachable")

    def archive(self, message: TaskMessage) -> None:
        raise BusFailClosed("bus unreachable")

    def ack(self, message: TaskMessage, *, success: bool) -> None:
        raise BusFailClosed("bus unreachable")

    def poison(self, message: TaskMessage) -> None:
        raise BusFailClosed("bus unreachable")


def _write_harness(repo: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    fake = json.dumps([sys.executable, str(FAKE)])
    (repo / "harness.toml").write_text(
        "\n".join(
            [
                'profile = "work"',
                'default = "fake"',
                'overflow = ""',
                "deny = []",
                'permissions = "repo-only"',
                'classification = "internal"',
                "",
                "[agents.fake]",
                f"command = {fake}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_user_config(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(
        "\n".join(
            [
                'default_profile = "work"',
                "audit_bodies = false",
                "",
                "[profiles.work]",
                'home = "~/.ravand/profiles/work"',
                'allow = ["fake", "grok", "kimi"]',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _audit_events(root: Path) -> list[dict[str, object]]:
    path = root / "audit.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_file_policy_store_is_reachable(tmp_path: Path) -> None:
    home = tmp_path / "home"
    repo = tmp_path / "repo"
    _write_user_config(home)
    _write_harness(repo)
    store = FilePolicyStore()
    store.require_reachable(home=home, cwd=repo)


def test_down_policy_store_fails_closed(tmp_path: Path) -> None:
    store = DownPolicyStore()
    with pytest.raises(FailClosed, match="policy unreachable"):
        store.require_reachable(home=tmp_path, cwd=tmp_path)


def test_policy_store_down_resolve_fails_closed_no_soft_deny(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_harness(repo)
    _write_user_config(home)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with pytest.raises(FailClosed, match="policy unreachable"):
        resolve(repo, store=DownPolicyStore())


def test_policy_store_down_run_does_not_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_harness(repo)
    _write_user_config(home)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    marker = tmp_path / "spawned-after-policy-down"
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    env["FAKE_ACP_STATE"] = str(marker)
    # Inject down store via env consumed by resolve path in CLI/run.
    env["RAVAND_POLICY_STORE"] = "down"
    result = subprocess.run(
        [
            "uv",
            "run",
            "ravand",
            "run",
            "--format",
            "jsonl",
            "should not spawn",
        ],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert result.returncode == 3
    assert not marker.exists()
    assert "sk-" not in result.stdout + result.stderr
    events = _audit_events(home)
    assert any(e.get("type") == "agent.denied" for e in events)


def test_down_bus_require_reachable_fails_closed() -> None:
    bus = DownBus()
    with pytest.raises(BusFailClosed, match="bus unreachable"):
        bus.require_reachable()


def test_memory_bus_require_reachable_ok() -> None:
    Bus().require_reachable()


def test_bus_down_dispatch_fails_closed_no_enqueue_audits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_harness(repo)
    _write_user_config(home)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    store = SessionStore(home)
    with pytest.raises(BusFailClosed, match="bus unreachable"):
        dispatch(
            repo,
            "should not queue",
            bus=DownBus(),  # type: ignore[arg-type]
            store=store,
            task_id="task-down",
            audit=AuditLog(home),
        )
    assert list((home / "sessions").glob("*.json")) == []
    events = _audit_events(home)
    assert any(e.get("type") == "agent.denied" for e in events)
    assert events[0]["taskId"] == "task-down"


def test_bus_down_run_prompt_does_not_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_harness(repo)
    _write_user_config(home)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    policy = resolve(repo)
    marker = tmp_path / "spawned-after-bus-down"
    monkeypatch.setenv("FAKE_ACP_STATE", str(marker))
    events: list[dict] = []

    def sink(event: dict) -> None:
        events.append(event)

    with pytest.raises(BusFailClosed, match="bus unreachable"):
        run_prompt(
            policy,
            "should not spawn",
            cwd=repo,
            sink=sink,
            bus=DownBus(),  # type: ignore[arg-type]
        )
    assert not marker.exists()
    assert events == []
    audited = _audit_events(home)
    assert any(e.get("type") == "agent.denied" for e in audited)


def test_audit_agent_denied_records_unreachable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("RAVAND_HOME", str(home))
    audit_agent_denied("policy unreachable", cwd=tmp_path / "repo")
    events = _audit_events(home)
    assert len(events) == 1
    assert events[0]["type"] == "agent.denied"
    assert "unreachable" in str(events[0].get("detail", ""))
