"""Sandbox seam: parse harness sandbox, fail closed on customer+none and container."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from ravand_policy import PolicyDenied, resolve

ROOT = Path(__file__).resolve().parents[1]


def _write_harness(
    repo: Path,
    *,
    profile: str = "work",
    default: str = "grok",
    classification: str = "internal",
    permissions: str = "repo-only",
    sandbox: str | None = None,
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    lines = [
        f'profile = "{profile}"',
        f'default = "{default}"',
        'overflow = ""',
        "deny = []",
        f'permissions = "{permissions}"',
        f'classification = "{classification}"',
    ]
    if sandbox is not None:
        lines.append(f'sandbox = "{sandbox}"')
    lines.extend(
        [
            "",
            "[agents.grok]",
            'command = ["grok", "agent", "stdio"]',
            "",
        ]
    )
    (repo / "harness.toml").write_text("\n".join(lines), encoding="utf-8")


def _which(cwd: Path, home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    return subprocess.run(
        ["uv", "run", "ravand", "which"],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_which_defaults_sandbox_to_repo_only(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_harness(repo)
    result = _which(repo, tmp_path / "home")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["sandbox"] == "repo-only"


def test_which_includes_explicit_sandbox(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_harness(repo, sandbox="none")
    result = _which(repo, tmp_path / "home")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["sandbox"] == "none"


def test_customer_sandbox_none_with_writes_allowed_denied(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_harness(
        repo,
        classification="customer",
        sandbox="none",
        permissions="repo-only",
    )
    result = _which(repo, tmp_path / "home")
    assert result.returncode == 3
    assert "sandbox" in result.stderr.lower()


def test_customer_sandbox_none_deny_writes_allowed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_harness(
        repo,
        classification="customer",
        sandbox="none",
        permissions="deny-writes",
    )
    result = _which(repo, tmp_path / "home")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["sandbox"] == "none"


def test_sandbox_container_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_harness(repo, sandbox="container")
    result = _which(repo, tmp_path / "home")
    assert result.returncode == 3
    assert "container" in result.stderr.lower()


def test_resolve_customer_sandbox_none_repo_only_raises(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repo = tmp_path / "repo"
    _write_harness(
        repo,
        classification="customer",
        sandbox="none",
        permissions="repo-only",
    )
    monkeypatch.setenv("RAVAND_HOME", str(tmp_path / "home"))
    with pytest.raises(PolicyDenied, match="sandbox"):
        resolve(repo)


def test_internal_sandbox_none_allowed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_harness(repo, sandbox="none")
    result = _which(repo, tmp_path / "home")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["sandbox"] == "none"
