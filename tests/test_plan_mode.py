"""Plan mode: human=plan denies writes/shell until plan.allow (#103)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "support" / "fake_acp_agent.py"


def _harness(
    repo: Path,
    *,
    human: str | None = "plan",
    permissions: str = "repo-only",
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    fake = json.dumps([sys.executable, str(FAKE)])
    lines = [
        'profile = "work"',
        'default = "fake"',
        'overflow = ""',
        "deny = []",
        f'permissions = "{permissions}"',
        'classification = "internal"',
        "",
        "[agents.fake]",
        f"command = {fake}",
        "",
    ]
    if human is not None:
        lines.insert(6, f'human = "{human}"')
    (repo / "harness.toml").write_text("\n".join(lines), encoding="utf-8")


def _run(
    repo: Path,
    home: Path,
    prompt: str,
    *,
    extra_env: dict[str, str] | None = None,
    extra_args: list[str] | None = None,
    stdin: str | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    env.update(extra_env or {})
    return subprocess.run(
        ["uv", "run", "ravand", "run", "--format", "jsonl", *(extra_args or []), prompt],
        cwd=repo,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def _events(stdout: str) -> list[dict]:
    return [json.loads(ln) for ln in stdout.splitlines() if ln.strip()]


def _audit_types(home: Path) -> list[str]:
    audit_path = home / "audit.jsonl"
    if not audit_path.is_file():
        return []
    return [
        json.loads(line)["type"]
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_plan_mode_emits_plan_ready_and_denies_write_without_approval(
    tmp_path: Path,
) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    result = _run(repo, home, "write /etc/passwd", extra_env={"RAVAND_PLAN_TIMEOUT": "0"})
    assert result.returncode == 0, result.stderr
    events = _events(result.stdout)
    types = [e.get("type") for e in events]
    assert "plan.ready" in types
    assert "plan.allow" not in _audit_types(home)
    assert "plan.deny" in _audit_types(home)


def test_plan_allow_audits_then_broker_denies_outside_repo(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    result = _run(repo, home, "write /etc/passwd", stdin="y\n")
    assert result.returncode == 0, result.stderr
    events = _events(result.stdout)
    assert "plan.ready" in [e.get("type") for e in events]
    types = _audit_types(home)
    assert "plan.allow" in types
    assert "permission.deny" in types


def test_plan_deny_audits_on_rejection(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    result = _run(
        repo,
        home,
        "write /etc/passwd",
        extra_env={"RAVAND_ASK": "1"},
        stdin="n\n",
    )
    assert result.returncode == 0, result.stderr
    assert "plan.deny" in _audit_types(home)
    assert "plan.allow" not in _audit_types(home)


def test_yes_does_not_auto_approve_plan(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    result = _run(repo, home, "write /etc/passwd", extra_args=["--yes"])
    assert result.returncode == 0, result.stderr
    events = _events(result.stdout)
    assert "plan.ready" in [e.get("type") for e in events]
    assert "plan.allow" not in _audit_types(home)
    assert "plan.deny" in _audit_types(home)


def test_permissions_plan_without_human(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo, human=None, permissions="plan")
    result = _run(repo, home, "write /etc/passwd", extra_env={"RAVAND_PLAN_TIMEOUT": "0"})
    assert result.returncode == 0, result.stderr
    events = _events(result.stdout)
    assert "plan.ready" in [e.get("type") for e in events]
    assert "plan.deny" in _audit_types(home)
