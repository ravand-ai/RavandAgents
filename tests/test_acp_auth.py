"""ACP handshake auth timeout: initialize/authenticate must not block forever (#195)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _hang_auth_agent(path: Path) -> None:
    """Fake ACP child: answers initialize with authMethods, never answers authenticate."""
    path.write_text(
        textwrap.dedent(
            """\
            import json
            import sys
            import time

            while True:
                line = sys.stdin.readline()
                if not line:
                    break
                msg = json.loads(line)
                method = msg.get("method")
                mid = msg.get("id")
                if method == "initialize":
                    sys.stdout.write(
                        json.dumps(
                            {
                                "jsonrpc": "2.0",
                                "id": mid,
                                "result": {
                                    "protocolVersion": 1,
                                    "authMethods": [
                                        {"id": "cached_token", "name": "Cached token"}
                                    ],
                                },
                            }
                        )
                        + "\\n"
                    )
                    sys.stdout.flush()
                elif method == "authenticate":
                    time.sleep(3600)
            """
        ),
        encoding="utf-8",
    )


def _harness(repo: Path, agent_script: Path) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    cmd = json.dumps([sys.executable, str(agent_script)])
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
                f"command = {cmd}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_authenticate_hang_exits_2_with_auth_missing(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    agent = tmp_path / "hang_auth_agent.py"
    _hang_auth_agent(agent)
    _harness(repo, agent)

    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    env["RAVAND_ACP_HANDSHAKE_TIMEOUT"] = "1"

    result = subprocess.run(
        ["uv", "run", "ravand", "run", "--format", "jsonl", "say hi"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 2, result.stderr
    assert "login" in result.stderr.lower()

    audit_path = home / "audit.jsonl"
    assert audit_path.is_file()
    audit_types = [
        json.loads(line)["type"]
        for line in audit_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert "auth.missing" in audit_types
    assert not list((home / "sessions").glob("*.json"))
