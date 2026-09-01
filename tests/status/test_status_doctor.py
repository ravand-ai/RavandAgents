"""Failing contracts for `ravand status` (login doctor). Slice 0 is not implemented."""

from __future__ import annotations

from pathlib import Path

from .support import REPO_ROOT, combined_output, run_ravand_status

LOGIN_STATES = ("logged-in", "missing", "unknown")


def test_status_exits_zero(isolated_home: Path) -> None:
    result = run_ravand_status(cwd=REPO_ROOT, home=isolated_home)
    assert result.returncode == 0, combined_output(result)


def test_status_prints_profile_and_home(isolated_home: Path) -> None:
    result = run_ravand_status(cwd=REPO_ROOT, home=isolated_home)
    text = combined_output(result).lower()
    assert result.returncode == 0, combined_output(result)
    assert "profile" in text
    assert "work" in text
    assert "home" in text
    assert "profiles/work" in text or str(
        isolated_home / ".ravand" / "profiles" / "work"
    ).lower() in text


def test_status_prints_agent_login_state(isolated_home: Path) -> None:
    result = run_ravand_status(cwd=REPO_ROOT, home=isolated_home)
    text = combined_output(result).lower()
    assert result.returncode == 0, combined_output(result)
    assert any(state in text for state in LOGIN_STATES), text
    for agent in ("grok", "kimi", "cursor"):
        assert agent in text


def test_status_this_repo_shows_work_default_overflow_and_registered_cursor(
    isolated_home: Path,
) -> None:
    result = run_ravand_status(cwd=REPO_ROOT, home=isolated_home)
    text = combined_output(result).lower()
    assert result.returncode == 0, combined_output(result)
    assert "work" in text
    assert "default" in text and "grok" in text
    assert "overflow" in text and "kimi" in text
    assert "cursor" in text
    assert "registered" in text


def test_status_customer_personal_is_denied(isolated_home: Path, tmp_path: Path) -> None:
    repo = tmp_path / "customer-repo"
    repo.mkdir()
    (repo / "harness.toml").write_text(
        "\n".join(
            [
                'profile = "personal"',
                'default = "kimi"',
                'overflow = ""',
                "deny = []",
                'permissions = "repo-only"',
                'classification = "customer"',
                "",
                "[agents.kimi]",
                'command = ["kimi", "acp"]',
                "",
            ]
        ),
        encoding="utf-8",
    )
    result = run_ravand_status(cwd=repo, home=isolated_home)
    text = combined_output(result).lower()
    assert "denied" in text
    assert "not implemented" not in text
