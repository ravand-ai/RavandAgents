"""Fail-closed security contracts (GitHub issue #1).

Source of law: docs/SECURITY.md ("Checks that must pass on every change").

These tests call the real APIs that exist on this branch:

- ``ravand_policy.resolve(cwd, profile_override=..., agent_override=...)``
  raising the typed errors ``PolicyDenied`` / ``UnknownAgent``
  (both subclasses of ``FailClosed``).
- ``ravand_permissions.decide_repo_only(tool_call, cwd)`` for the
  permission broker deny (lands with Slice 2; parked until then).
- ``ravand run --format jsonl`` for the machine stream (Slice 2;
  parked while the command is ``not implemented``).

Fail-closed rule: when policy, permission, or agent resolution cannot
decide, the error must be raised BEFORE any spawn. There is no soft deny.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from ravand_policy import FailClosed, PolicyDenied, UnknownAgent, resolve

# Patterns that must never appear in a machine-readable JSONL stream
# (docs/SECURITY.md check 5: no keys, no cookie HOME paths).
FORBIDDEN_STREAM_PATTERNS = ("sk-", "xai-", "Bearer", ".claude")

ROOT = Path(__file__).resolve().parents[2]


def _write_harness(
    repo: Path,
    *,
    profile: str,
    default: str = "kimi",
    classification: str = "internal",
) -> None:
    """Minimal harness.toml pinned to one profile/agent (SCHEMA.md shape)."""
    repo.mkdir(parents=True, exist_ok=True)
    (repo / "harness.toml").write_text(
        "\n".join(
            [
                f'profile = "{profile}"',
                f'default = "{default}"',
                'overflow = ""',
                "deny = []",
                'permissions = "repo-only"',
                f'classification = "{classification}"',
                "",
                "[agents.kimi]",
                'command = ["fake-agent", "acp"]',
                "",
            ]
        ),
        encoding="utf-8",
    )


def _write_user_config(home: Path) -> None:
    """Mirror of examples/policy.user.toml (no secrets, per SCHEMA)."""
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(
        "\n".join(
            [
                'default_profile = "personal"',
                "audit_bodies = false",
                "",
                "[profiles.work]",
                'home = "~/.ravand/profiles/work"',
                'allow = ["claude", "grok", "cursor"]',
                "",
                "[profiles.personal]",
                'home = "~/.ravand/profiles/personal"',
                'allow = ["kimi", "grok", "opencode", "dsh"]',
                "",
            ]
        ),
        encoding="utf-8",
    )


@pytest.fixture
def ravand_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Isolated RAVAND_HOME + repo dir; nothing touches ~/.ravand."""
    home = tmp_path / "ravand-home"
    _write_user_config(home)
    monkeypatch.setenv("RAVAND_HOME", str(home))
    return tmp_path / "repo"


# docs/SECURITY.md check 2: personal repo + work override -> denied.
def test_personal_repo_rejects_work_profile_override(ravand_env: Path) -> None:
    _write_harness(ravand_env, profile="personal")
    with pytest.raises(PolicyDenied):
        resolve(ravand_env, profile_override="work")


def test_work_repo_rejects_personal_profile_override(ravand_env: Path) -> None:
    """The reverse direction must fail closed too (AGENTS.md hard rule)."""
    _write_harness(ravand_env, profile="work", default="kimi")
    with pytest.raises(PolicyDenied):
        resolve(ravand_env, profile_override="personal")


def test_profile_mismatch_is_fail_closed(ravand_env: Path) -> None:
    """PolicyDenied is a FailClosed error: no soft deny path exists."""
    _write_harness(ravand_env, profile="personal")
    with pytest.raises(FailClosed):
        resolve(ravand_env, profile_override="work")


def test_customer_classification_rejects_personal_profile(
    ravand_env: Path,
) -> None:
    """Customer data never runs on a personal account (SECURITY.md)."""
    _write_harness(ravand_env, profile="personal", classification="customer")
    with pytest.raises(PolicyDenied):
        resolve(ravand_env)


# docs/SECURITY.md check 3: write /etc/passwd -> denied.
def test_write_etc_passwd_is_denied(tmp_path: Path) -> None:
    permissions = pytest.importorskip(
        "ravand_permissions",
        reason="permission broker package missing",
    )
    decide = getattr(permissions, "decide_repo_only", None)
    if decide is None:
        pytest.skip("permission broker lands with Slice 2; contract parked")
    verdict = decide(
        {"kind": "write", "rawInput": {"path": "/etc/passwd"}},
        cwd=str(tmp_path),
    )
    assert verdict == "deny", "write outside cwd must be denied, never asked"


def test_write_inside_repo_is_allowed(tmp_path: Path) -> None:
    """Sanity counterpart: repo-only mode permits writes under cwd."""
    permissions = pytest.importorskip(
        "ravand_permissions",
        reason="permission broker package missing",
    )
    decide = getattr(permissions, "decide_repo_only", None)
    if decide is None:
        pytest.skip("permission broker lands with Slice 2; contract parked")
    verdict = decide(
        {"kind": "write", "rawInput": {"path": str(tmp_path / "ok.txt")}},
        cwd=str(tmp_path),
    )
    assert verdict == "allow"


# docs/SECURITY.md check 4: unknown agent id -> error, no spawn.
def test_unknown_agent_id_errors_before_spawn(ravand_env: Path) -> None:
    _write_harness(ravand_env, profile="personal", default="kimi")
    with pytest.raises(UnknownAgent):
        resolve(ravand_env, agent_override="does-not-exist")
    # Fail-closed note: resolution happens before spawn, so a raise here
    # guarantees no process is started for an unknown agent id.


def test_unknown_agent_exit_code_is_not_ok(ravand_env: Path) -> None:
    """CLI surface: `ravand which -a bogus` exits non-zero, prints no JSON."""
    _write_harness(ravand_env, profile="personal", default="kimi")
    env = os.environ.copy()
    result = subprocess.run(
        [sys.executable, "-m", "ravand_cli.cli", "which", "-a", "does-not-exist"],
        cwd=ravand_env,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)


# docs/SECURITY.md check 5: JSONL stream must not leak secrets.
def test_jsonl_stream_contains_no_secrets(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_harness(repo, profile="personal")
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(tmp_path / "home")
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "ravand_cli.cli",
            "run",
            "--format",
            "jsonl",
            "echo the word sk-probe",
        ],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    out = result.stdout + result.stderr
    # Slice 1 base: `run` prints "not implemented" or rejects --format.
    if "not implemented" in out.lower() or "unrecognized arguments" in out:
        pytest.skip("ravand run lands with Slice 2; stream contract parked")
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        event = json.loads(line)  # every stream line must be valid JSON
        text = json.dumps(event)
        for pattern in FORBIDDEN_STREAM_PATTERNS:
            assert pattern not in text, f"stream leaked {pattern!r}: {line}"
    for pattern in FORBIDDEN_STREAM_PATTERNS:
        assert pattern not in result.stderr


# TODO(extra work, not this issue):
# - audit.jsonl redaction contract for profile="work" (needs Slice 3).
# - subagent grant narrowing: child of a repo-read parent must not inherit
#   write/shell (docs/SECURITY.md "Subagents").
# - profile HOME cookie files must never be opened by product code, only
#   stat'ed for login doctor (docs/SECURITY.md check 1).
