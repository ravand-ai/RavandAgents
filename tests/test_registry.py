"""Issue #8 TDD: registry wires kimi and cursor ACP backends like grok.

Registry is the adapter catalog (HLD: "Data, not logic"). These tests pin
the canonical command table and prove the CLI resolves kimi/cursor through
the same path as grok, with fail-closed behavior for unknown or denied ids.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from ravand_registry import AGENT_COMMANDS, agent_command

ROOT = Path(__file__).resolve().parents[1]


# --- Catalog: the same ids the HLD Registry table lists -------------------

def test_catalog_has_grok_kimi_cursor():
    assert AGENT_COMMANDS["grok"] == ["grok", "agent", "stdio"]
    assert AGENT_COMMANDS["kimi"] == ["kimi", "acp"]
    assert AGENT_COMMANDS["cursor"] == ["cursor-agent", "acp"]


def test_agent_command_returns_acp_shape():
    # Every wired backend is a vendor ACP command, never an HTTP wrap.
    for agent_id in ("grok", "kimi", "cursor"):
        command = agent_command(agent_id)
        assert isinstance(command, list)
        assert all(isinstance(part, str) for part in command)
        assert command, agent_id


def test_unknown_agent_id_returns_none_fail_closed():
    # Data, not logic: the registry signals "cannot decide" with None so
    # the caller (policy) raises UnknownAgent before any spawn.
    assert agent_command("does-not-exist") is None


# --- CLI wiring: kimi and cursor resolve the same way as grok --------------

def _which(cwd: Path, home: Path, extra: list[str]) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    return subprocess.run(
        ["uv", "run", "ravand", "which", *extra],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_which_lists_kimi_command_array(tmp_path: Path) -> None:
    result = _which(ROOT, tmp_path / "home", ["-a", "kimi"])
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["agent"] == "kimi"
    assert data["command"] == ["kimi", "acp"]


def test_which_lists_cursor_command_array(tmp_path: Path) -> None:
    result = _which(ROOT, tmp_path / "home", ["-a", "cursor"])
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["agent"] == "cursor"
    assert data["command"] == ["cursor-agent", "acp"]


def test_unknown_id_errors_no_spawn(tmp_path: Path) -> None:
    result = _which(ROOT, tmp_path / "home", ["-a", "bogus"])
    assert result.returncode != 0
    assert not result.stdout.strip(), "no JSON payload for an unknown id"


def test_deny_list_blocks_cursor(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "harness.toml").write_text(
        "\n".join(
            [
                'profile = "work"',
                'default = "grok"',
                'overflow = ""',
                'deny = ["cursor"]',
                'permissions = "repo-only"',
                'classification = "internal"',
                "",
                "[agents.grok]",
                'command = ["grok", "agent", "stdio"]',
                "",
                "[agents.cursor]",
                'command = ["cursor-agent", "acp"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    result = _which(repo, tmp_path / "home", ["-a", "cursor"])
    assert result.returncode == 3, result.stderr
    assert not result.stdout.strip()
