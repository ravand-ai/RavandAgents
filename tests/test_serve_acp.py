"""Issue #107: ravand serve acp stdio ACP server."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAKE = ROOT / "tests" / "support" / "fake_acp_agent.py"
FORBIDDEN = ("sk-", "xai-", "Bearer", "cookies")


def _harness(
    repo: Path,
    *,
    profile: str = "work",
    deny: list[str] | None = None,
    classification: str = "internal",
) -> None:
    repo.mkdir(parents=True, exist_ok=True)
    fake = json.dumps([sys.executable, str(FAKE)])
    deny_json = json.dumps(deny or [])
    (repo / "harness.toml").write_text(
        "\n".join(
            [
                f'profile = "{profile}"',
                'default = "fake"',
                'overflow = ""',
                f"deny = {deny_json}",
                'permissions = "repo-only"',
                f'classification = "{classification}"',
                "",
                "[agents.fake]",
                f"command = {fake}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _user_config(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "config.toml").write_text(
        "\n".join(
            [
                'default_profile = "personal"',
                "audit_bodies = false",
                "",
                "[profiles.work]",
                'home = "~/.ravand/profiles/work"',
                'allow = ["claude", "grok", "cursor", "fake"]',
                "",
                "[profiles.personal]",
                'home = "~/.ravand/profiles/personal"',
                'allow = ["kimi", "grok", "opencode", "dsh", "fake"]',
                "",
            ]
        ),
        encoding="utf-8",
    )


class AcpFakeClient:
    """Minimal ACP client talking NDJSON JSON-RPC over a subprocess stdio pipe."""

    def __init__(self, proc: subprocess.Popen[str]) -> None:
        self._proc = proc
        self._next_id = 0

    def close(self) -> None:
        if self._proc.stdin:
            self._proc.stdin.close()
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()

    def _send(self, method: str, params: dict) -> int:
        rid = self._next_id
        self._next_id += 1
        msg = {"jsonrpc": "2.0", "id": rid, "method": method, "params": params}
        assert self._proc.stdin is not None
        self._proc.stdin.write(json.dumps(msg) + "\n")
        self._proc.stdin.flush()
        return rid

    def _read(self) -> dict | None:
        assert self._proc.stdout is not None
        line = self._proc.stdout.readline()
        if not line:
            return None
        return json.loads(line)

    def request(self, method: str, params: dict) -> dict:
        rid = self._send(method, params)
        updates: list[dict] = []
        while True:
            msg = self._read()
            if msg is None:
                raise AssertionError(f"EOF waiting for {method}")
            if msg.get("method") == "session/update":
                updates.append(msg)
                continue
            if msg.get("id") == rid and "result" in msg:
                return {"result": msg["result"], "updates": updates}
            if msg.get("id") == rid and "error" in msg:
                return {"error": msg["error"], "updates": updates}
            if msg.get("id") is not None and "result" in msg:
                continue


def _serve(repo: Path, home: Path) -> AcpFakeClient:
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    proc = subprocess.Popen(
        ["uv", "run", "ravand", "serve", "acp"],
        cwd=repo,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return AcpFakeClient(proc)


def test_serve_acp_handshake_and_prompt(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    _user_config(home)
    client = _serve(repo, home)
    try:
        init = client.request(
            "initialize",
            {
                "protocolVersion": 1,
                "clientCapabilities": {},
                "clientInfo": {"name": "test-client", "version": "0"},
            },
        )
        assert "error" not in init, init
        result = init["result"]
        assert result.get("protocolVersion") == 1
        agent_info = result.get("agentInfo") or {}
        assert agent_info.get("name") == "ravand"

        session = client.request(
            "session/new",
            {"cwd": str(repo.resolve()), "mcpServers": []},
        )
        assert "error" not in session, session
        session_id = session["result"]["sessionId"]
        assert session_id

        prompt = client.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "say hi"}],
            },
        )
        assert "error" not in prompt, prompt
        assert prompt["result"].get("stopReason") == "end_turn"
        texts = [
            (u.get("params") or {}).get("update", {}).get("content", {})
            for u in prompt["updates"]
        ]
        flat = json.dumps(texts)
        assert "hello-from-fake" in flat
    finally:
        client.close()


def test_serve_acp_stream_has_no_secrets(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo)
    _user_config(home)
    client = _serve(repo, home)
    try:
        client.request(
            "initialize",
            {"protocolVersion": 1, "clientCapabilities": {}},
        )
        session = client.request(
            "session/new",
            {"cwd": str(repo.resolve()), "mcpServers": []},
        )
        session_id = session["result"]["sessionId"]
        prompt = client.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "say hi"}],
            },
        )
        blob = json.dumps(prompt)
        for pattern in FORBIDDEN:
            assert pattern not in blob
    finally:
        client.close()


def test_serve_acp_policy_denied_before_spawn(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    home = tmp_path / "home"
    _harness(repo, profile="personal", classification="customer")
    _user_config(home)
    client = _serve(repo, home)
    try:
        client.request(
            "initialize",
            {"protocolVersion": 1, "clientCapabilities": {}},
        )
        session = client.request(
            "session/new",
            {"cwd": str(repo.resolve()), "mcpServers": []},
        )
        assert "error" not in session
        session_id = session["result"]["sessionId"]
        prompt = client.request(
            "session/prompt",
            {
                "sessionId": session_id,
                "prompt": [{"type": "text", "text": "say hi"}],
            },
        )
        assert "error" in prompt, prompt
    finally:
        client.close()
