"""Wire file memory into ravand run (GitHub issue #102)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from ravand_memory import FileStore

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "support" / "fake_acp_agent.py"
FORBIDDEN = ("sk-", "xai-", "Bearer", "cookies")


def _harness(
    repo: Path,
    *,
    profile: str = "work",
    memory: dict[str, str] | None = None,
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    fake = json.dumps([sys.executable, str(FAKE)])
    lines = [
        f'profile = "{profile}"',
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
    if memory is not None:
        lines.extend(
            [
                "[memory]",
                f'isolation = "{memory["isolation"]}"',
                f'store = "{memory["store"]}"',
                "",
            ]
        )
    (repo / "harness.toml").write_text("\n".join(lines), encoding="utf-8")


def _run(
    repo: Path,
    home: Path,
    prompt: str,
    *,
    extra_env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    env.update(extra_env or {})
    return subprocess.run(
        ["uv", "run", "ravand", "run", "--format", "jsonl", prompt],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def _events(stdout: str) -> list[dict]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def _notes(home: Path, *, isolation: str, scope_key: str) -> list[str]:
    return FileStore(home, isolation=isolation, scope_key=scope_key).read()


def test_same_scope_read_works(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo, memory={"isolation": "profile", "store": "file"})
    store = FileStore(home, isolation="profile", scope_key="work")
    store.write("prior-widget-decision")

    result = _run(
        repo,
        home,
        "continue build",
        extra_env={"FAKE_ACP_MEMORY_MARKER": "prior-widget-decision"},
    )
    assert result.returncode == 0, result.stderr
    events = _events(result.stdout)
    assert any(e.get("text") == "memory-read-ok" for e in events)
    notes = store.read()
    assert "prior-widget-decision" in notes
    assert "continue build" in notes


def test_other_profile_empty(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo, profile="personal", memory={"isolation": "profile", "store": "file"})
    FileStore(home, isolation="profile", scope_key="work").write("work-only note")

    result = _run(repo, home, "hello")
    assert result.returncode == 0, result.stderr
    personal_notes = _notes(home, isolation="profile", scope_key="personal")
    assert "work-only note" not in personal_notes
    assert "hello" in personal_notes


def test_no_memory_section_does_not_write_notes(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo, memory=None)
    result = _run(repo, home, "no memory here")
    assert result.returncode == 0, result.stderr
    memory_root = home / "memory"
    assert not memory_root.exists()


def test_unknown_memory_store_fails_closed(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo, memory={"isolation": "profile", "store": "postgres"})
    result = _run(repo, home, "should not spawn")
    assert result.returncode != 0
    assert "postgres" in result.stderr.lower() or "unknown" in result.stderr.lower()
    blob = result.stdout + result.stderr
    for marker in FORBIDDEN:
        assert marker not in blob
