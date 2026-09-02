"""Cron trigger: Policy then dispatch (GitHub issues #136, #210).

Source of law: docs/HLD.md Cron, docs/MODULAR.md Triggers, docs/SCHEMA.md [cron].
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from ravand_audit import AuditLog
from ravand_bus import Bus
from ravand_policy import PolicyDenied
from ravand_runtime.cron import fire_cron, load_cron_jobs, serve_cron
from ravand_sessions import SessionStore

ROOT = Path(__file__).resolve().parents[1]

QUEUE_TASKS = "q.tasks"
DUE = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)
NOT_DUE = datetime(2026, 9, 5, 9, 0, tzinfo=UTC)


def _write_harness(
    repo: Path,
    *,
    profile: str = "work",
    default: str = "grok",
    deny: str = "[]",
    classification: str = "internal",
    extra: str = "",
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "harness.toml").write_text(
        "\n".join(
            [
                f'profile = "{profile}"',
                f'default = "{default}"',
                'overflow = "kimi"',
                f"deny = {deny}",
                'permissions = "repo-only"',
                f'classification = "{classification}"',
                extra,
                "",
                "[agents.grok]",
                'command = ["grok", "agent", "stdio"]',
                "",
                "[agents.kimi]",
                'command = ["kimi", "acp"]',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_user_config(
    home: Path,
    *,
    accounts: dict[str, dict[str, str]] | None = None,
) -> None:
    home.mkdir(parents=True, exist_ok=True)
    lines = [
        'default_profile = "work"',
        "",
        "[profiles.work]",
        'home = "~/.ravand/profiles/work"',
        'allow = ["grok", "kimi"]',
        "",
    ]
    if accounts:
        for account_id, spec in accounts.items():
            lines.append(f"[accounts.{account_id}]")
            for key, value in spec.items():
                lines.append(f'{key} = "{value}"')
            lines.append("")
    (home / "config.toml").write_text("\n".join(lines), encoding="utf-8")


def _audit_events(root: Path) -> list[dict[str, object]]:
    path = root / "audit.jsonl"
    if not path.is_file():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_load_cron_jobs_from_harness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=(
            "[cron]\n"
            'jobs = [{ id = "morning", spec = "0 9 * * 1-5", prompt = "status" }]\n'
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    jobs = load_cron_jobs(repo)
    assert len(jobs) == 1
    assert jobs[0].id == "morning"
    assert jobs[0].spec == "0 9 * * 1-5"
    assert jobs[0].prompt == "status"


def test_missing_cron_section_is_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(repo)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    assert load_cron_jobs(repo) == []


def test_fire_due_job_dispatches_after_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=(
            "[cron]\n"
            'jobs = [{ id = "morning", spec = "0 9 * * 1-5", prompt = "status" }]\n'
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    fired = fire_cron(
        repo,
        now=DUE,
        bus=bus,
        store=store,
        audit=AuditLog(home),
    )
    assert [job.id for job in fired] == ["morning"]
    got = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert got is not None
    assert got.task_id == "morning:20260907T0900"
    assert got.prompt == "status"
    assert got.agent == "grok"
    assert got.profile == "work"
    assert got.cwd_hint == str(repo.resolve())
    assert list((home / "sessions").glob("*.json"))


def test_not_due_job_does_not_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=(
            "[cron]\n"
            'jobs = [{ id = "morning", spec = "0 9 * * 1-5", prompt = "status" }]\n'
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    fired = fire_cron(
        repo,
        now=NOT_DUE,
        bus=bus,
        store=store,
        audit=AuditLog(home),
    )
    assert fired == []
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert list((home / "sessions").glob("*.json")) == []


def test_account_mismatch_skips_and_audits_trigger_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_user_config(
        home,
        accounts={"grok-personal": {"kind": "cli", "agent": "grok"}},
    )
    _write_harness(
        repo,
        classification="customer",
        extra=(
            "[cron]\n"
            "jobs = [{ id = \"morning\", spec = \"0 9 * * 1-5\", "
            'prompt = "status", account = "grok-personal" }]\n'
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    fired = fire_cron(
        repo,
        now=DUE,
        bus=bus,
        store=store,
        audit=AuditLog(home),
    )
    assert fired == []
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    assert list((home / "sessions").glob("*.json")) == []
    events = _audit_events(home)
    assert [event["type"] for event in events] == ["trigger.denied"]
    assert events[0]["taskId"] == "morning"
    blob = (home / "audit.jsonl").read_text(encoding="utf-8")
    assert "sk-" not in blob


def test_classification_mismatch_skips_and_audits_trigger_denied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        classification="customer",
        extra=(
            "[cron]\n"
            "jobs = [{ id = \"morning\", spec = \"0 9 * * 1-5\", "
            'prompt = "status", classification = "internal" }]\n'
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    fired = fire_cron(
        repo,
        now=DUE,
        bus=bus,
        store=store,
        audit=AuditLog(home),
    )
    assert fired == []
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    events = _audit_events(home)
    assert [event["type"] for event in events] == ["trigger.denied"]
    assert events[0]["taskId"] == "morning"


def test_raw_key_in_job_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=(
            "[cron]\n"
            "jobs = [{ id = \"morning\", spec = \"0 9 * * 1-5\", "
            'prompt = "status", key = "sk-secret-value" }]\n'
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    with pytest.raises(PolicyDenied):
        load_cron_jobs(repo)
    bus = Bus()
    store = SessionStore(home)
    with pytest.raises(PolicyDenied):
        fire_cron(
            repo,
            now=DUE,
            bus=bus,
            store=store,
            audit=AuditLog(home),
        )
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    text = (repo / "harness.toml").read_text(encoding="utf-8")
    assert "sk-secret-value" in text


def _write_vault_secret(home: Path, ref: str, body: str) -> None:
    assert ref.startswith("vault:")
    path = home / "secrets" / ref.removeprefix("vault:")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")


def test_secret_ref_is_accepted(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=(
            "[cron]\n"
            "jobs = [{ id = \"morning\", spec = \"0 9 * * 1-5\", "
            'prompt = "status", secret_ref = "vault:work/cron" }]\n'
        ),
    )
    _write_vault_secret(home, "vault:work/cron", "cron-secret")
    monkeypatch.setenv("RAVAND_HOME", str(home))
    jobs = load_cron_jobs(repo)
    assert jobs[0].secret_ref == "vault:work/cron"
    bus = Bus()
    store = SessionStore(home)
    fired = fire_cron(
        repo,
        now=DUE,
        bus=bus,
        store=store,
        audit=AuditLog(home),
    )
    assert [job.id for job in fired] == ["morning"]
    got = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert got is not None
    assert got.prompt == "status"
    assert "sk-" not in got.prompt
    blob = (home / "audit.jsonl").read_text(encoding="utf-8") if (
        home / "audit.jsonl"
    ).is_file() else ""
    assert "cron-secret" not in blob


def test_missing_cron_secret_ref_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=(
            "[cron]\n"
            "jobs = [{ id = \"morning\", spec = \"0 9 * * 1-5\", "
            'prompt = "status", secret_ref = "vault:work/cron" }]\n'
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    jobs = load_cron_jobs(repo)
    assert jobs[0].secret_ref == "vault:work/cron"
    bus = Bus()
    store = SessionStore(home)
    fired = fire_cron(
        repo,
        now=DUE,
        bus=bus,
        store=store,
        audit=AuditLog(home),
    )
    assert fired == []
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    events = _audit_events(home)
    assert [event["type"] for event in events] == ["trigger.denied"]
    assert events[0]["taskId"] == "morning"
    blob = (home / "audit.jsonl").read_text(encoding="utf-8")
    assert "sk-" not in blob


def test_two_mondays_mint_distinct_task_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=(
            "[cron]\n"
            "jobs = [{ id = \"morning\", spec = \"0 9 * * 1-5\", "
            'prompt = "status" }]\n'
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    first = fire_cron(
        repo, now=DUE, bus=bus, store=store, audit=AuditLog(home)
    )
    later = datetime(2026, 9, 14, 9, 0, tzinfo=UTC)
    second = fire_cron(
        repo, now=later, bus=bus, store=store, audit=AuditLog(home)
    )
    assert [job.id for job in first] == ["morning"]
    assert [job.id for job in second] == ["morning"]
    ids = {bus.read(QUEUE_TASKS, visibility_timeout=600).task_id for _ in range(2)}
    assert ids == {"morning:20260907T0900", "morning:20260914T0900"}


def test_double_tick_same_minute_skips_second_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=(
            "[cron]\n"
            "jobs = [{ id = \"morning\", spec = \"0 9 * * 1-5\", "
            'prompt = "status" }, '
            '{ id = \"standdown\", spec = \"0 9 * * 1-5\", '
            'prompt = "later" }]\n'
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    first = fire_cron(
        repo, now=DUE, bus=bus, store=store, audit=AuditLog(home)
    )
    second = fire_cron(
        repo, now=DUE, bus=bus, store=store, audit=AuditLog(home)
    )
    assert [job.id for job in first] == ["morning", "standdown"]
    assert second == []
    got = {
        bus.read(QUEUE_TASKS, visibility_timeout=600).task_id for _ in range(2)
    }
    assert got == {"morning:20260907T0900", "standdown:20260907T0900"}
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None


def test_no_bus_still_runs_policy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _write_user_config(
        home,
        accounts={"grok-personal": {"kind": "cli", "agent": "grok"}},
    )
    _write_harness(
        repo,
        classification="customer",
        extra=(
            "[cron]\n"
            "jobs = [{ id = \"morning\", spec = \"0 9 * * 1-5\", "
            'prompt = "status", account = "grok-personal" }]\n'
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    fired = fire_cron(repo, now=DUE, audit=AuditLog(home))
    assert fired == []
    events = _audit_events(home)
    assert [event["type"] for event in events] == ["trigger.denied"]
    assert events[0]["taskId"] == "morning"
    assert list((home / "sessions").glob("*.json")) == []


def _ravand(
    *args: str, cwd: Path | None = None, env: dict | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "ravand", *args],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=15,
    )


def test_serve_cron_help_exists() -> None:
    result = _ravand("serve", "cron", "--help")
    assert result.returncode == 0, result.stderr
    combined = (result.stdout + result.stderr).lower()
    assert "usage" in combined
    assert "cron" in combined


def test_serve_cron_fails_closed_when_policy_unresolved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    home = tmp_path / "home"
    monkeypatch.setenv("RAVAND_HOME", str(home))
    slept: list[float] = []
    code = serve_cron(
        cwd=empty,
        now=DUE,
        interval=0,
        max_ticks=1,
        sleep=slept.append,
    )
    assert code != 0
    assert slept == []
    assert list((home / "sessions").glob("*.json")) == []


def test_cli_serve_cron_fail_closed_without_harness(tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    home = tmp_path / "home"
    env = dict(os.environ)
    env["RAVAND_HOME"] = str(home)
    result = _ravand("serve", "cron", cwd=empty, env=env)
    assert result.returncode != 0
    blob = (result.stdout + result.stderr).lower()
    assert "sk-" not in blob
    assert "xai-" not in blob
    assert "bearer" not in blob


def test_serve_cron_fires_due_job_without_sleeping_a_minute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=(
            "[cron]\n"
            'jobs = [{ id = "morning", spec = "0 9 * * 1-5", prompt = "status" }]\n'
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    slept: list[float] = []
    code = serve_cron(
        cwd=repo,
        now=DUE,
        interval=0,
        max_ticks=1,
        bus=bus,
        store=store,
        audit=AuditLog(home),
        sleep=slept.append,
    )
    assert code == 0
    assert all(seconds < 60 for seconds in slept)
    got = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert got is not None
    assert got.task_id == "morning:20260907T0900"
    assert got.prompt == "status"
    assert got.agent == "grok"


def test_serve_cron_loop_uses_injected_interval(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        extra=(
            "[cron]\n"
            'jobs = [{ id = "morning", spec = "0 9 * * 1-5", prompt = "status" }]\n'
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    slept: list[float] = []
    code = serve_cron(
        cwd=repo,
        now=DUE,
        interval=0,
        max_ticks=2,
        bus=bus,
        store=store,
        audit=AuditLog(home),
        sleep=slept.append,
    )
    assert code == 0
    assert slept == [0]
    got = bus.read(QUEUE_TASKS, visibility_timeout=600)
    assert got is not None
    assert got.task_id == "morning:20260907T0900"
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None


def test_serve_cron_classification_mismatch_skips_and_audits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    home.mkdir()
    _write_harness(
        repo,
        classification="customer",
        extra=(
            "[cron]\n"
            "jobs = [{ id = \"morning\", spec = \"0 9 * * 1-5\", "
            'prompt = "status", classification = "internal" }]\n'
        ),
    )
    monkeypatch.setenv("RAVAND_HOME", str(home))
    bus = Bus()
    store = SessionStore(home)
    code = serve_cron(
        cwd=repo,
        now=DUE,
        interval=0,
        max_ticks=1,
        bus=bus,
        store=store,
        audit=AuditLog(home),
        sleep=lambda _seconds: None,
    )
    assert code == 0
    assert bus.read(QUEUE_TASKS, visibility_timeout=600) is None
    events = _audit_events(home)
    assert [event["type"] for event in events] == ["trigger.denied"]
    assert events[0]["taskId"] == "morning"
    blob = (home / "audit.jsonl").read_text(encoding="utf-8")
    assert "sk-" not in blob
