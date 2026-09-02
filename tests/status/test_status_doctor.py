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


def test_status_grok_missing_without_auth_json(isolated_home: Path) -> None:
    result = run_ravand_status(cwd=REPO_ROOT, home=isolated_home)
    text = combined_output(result).lower()
    assert result.returncode == 0, combined_output(result)
    grok_line = next(
        (line for line in text.splitlines() if line.startswith("grok")),
        "",
    )
    assert grok_line, combined_output(result)
    assert "missing" in grok_line
    assert "logged-in" not in grok_line


def test_status_grok_logged_in_when_auth_json_exists(isolated_home: Path) -> None:
    auth = (
        isolated_home
        / ".ravand"
        / "profiles"
        / "work"
        / ".grok"
        / "auth.json"
    )
    auth.parent.mkdir(parents=True, exist_ok=True)
    auth.write_text("{}", encoding="utf-8")
    result = run_ravand_status(cwd=REPO_ROOT, home=isolated_home)
    text = combined_output(result).lower()
    assert result.returncode == 0, combined_output(result)
    grok_line = next(
        (line for line in text.splitlines() if line.startswith("grok")),
        "",
    )
    assert "logged-in" in grok_line, combined_output(result)


def _agent_line(text: str, name: str) -> str:
    return next((line for line in text.splitlines() if line.startswith(name)), "")


def test_status_claude_missing_even_if_npx_on_path(isolated_home: Path) -> None:
    result = run_ravand_status(cwd=REPO_ROOT, home=isolated_home)
    text = combined_output(result).lower()
    assert result.returncode == 0, combined_output(result)
    line = _agent_line(text, "claude")
    assert line, combined_output(result)
    assert "logged-in" not in line
    assert "missing" in line


def test_status_cursor_missing_without_marker(isolated_home: Path) -> None:
    result = run_ravand_status(cwd=REPO_ROOT, home=isolated_home)
    text = combined_output(result).lower()
    assert result.returncode == 0, combined_output(result)
    line = _agent_line(text, "cursor")
    assert line, combined_output(result)
    assert "logged-in" not in line
    assert "missing" in line


def test_status_cursor_logged_in_when_cursor_dir_has_file(
    isolated_home: Path,
) -> None:
    marker = (
        isolated_home
        / ".ravand"
        / "profiles"
        / "work"
        / ".cursor"
        / "argv.json"
    )
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}", encoding="utf-8")
    result = run_ravand_status(cwd=REPO_ROOT, home=isolated_home)
    text = combined_output(result).lower()
    assert result.returncode == 0, combined_output(result)
    line = _agent_line(text, "cursor")
    assert "logged-in" in line, combined_output(result)


def test_status_gh_missing_without_hosts_yml(isolated_home: Path) -> None:
    result = run_ravand_status(cwd=REPO_ROOT, home=isolated_home)
    text = combined_output(result).lower()
    assert result.returncode == 0, combined_output(result)
    line = _agent_line(text, "gh:")
    assert line, combined_output(result)
    assert "missing" in line
    assert "logged-in" not in line


def test_status_gh_logged_in_when_hosts_yml_exists(isolated_home: Path) -> None:
    hosts = (
        isolated_home
        / ".ravand"
        / "profiles"
        / "work"
        / ".config"
        / "gh"
        / "hosts.yml"
    )
    hosts.parent.mkdir(parents=True, exist_ok=True)
    hosts.write_text("github.com:\n", encoding="utf-8")
    result = run_ravand_status(cwd=REPO_ROOT, home=isolated_home)
    text = combined_output(result).lower()
    assert result.returncode == 0, combined_output(result)
    line = _agent_line(text, "gh:")
    assert "logged-in" in line, combined_output(result)


def test_status_empty_dir_tells_human_to_run_init(
    isolated_home: Path, tmp_path: Path
) -> None:
    repo = tmp_path / "empty"
    repo.mkdir()
    result = run_ravand_status(cwd=repo, home=isolated_home)
    text = combined_output(result)
    assert "traceback" not in text.lower()
    assert result.returncode != 0 or "ravand init" in text


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
