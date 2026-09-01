"""ACP v1 stdio server: one agent named ravand, fronting policy + run."""

from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any, TextIO

from ravand_policy import PolicyDenied, UnknownAgent, resolve
from ravand_runtime.run import audit_agent_denied, run_prompt

_AGENT_NAME = "ravand"
_AGENT_VERSION = "0.0.0"


def _read(stdin: TextIO) -> dict[str, Any] | None:
    line = stdin.readline()
    if not line:
        return None
    if line.lower().startswith("content-length"):
        n = int(line.split(":")[1])
        while True:
            blank = stdin.readline()
            if blank in ("\r\n", "\n", ""):
                break
        raw = stdin.read(n)
        return json.loads(raw)
    return json.loads(line)


def _write(stdout: TextIO, msg: dict[str, Any]) -> None:
    stdout.write(json.dumps(msg, separators=(",", ":")) + "\n")
    stdout.flush()


def _prompt_text(params: dict[str, Any]) -> str:
    prompt = params.get("prompt")
    if not isinstance(prompt, list):
        return ""
    parts: list[str] = []
    for block in prompt:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "\n".join(parts).strip()


def _policy_error(exc: PolicyDenied | UnknownAgent) -> dict[str, Any]:
    return {
        "code": -32000,
        "message": str(exc),
    }


def serve_acp(
    *,
    stdin: TextIO | None = None,
    stdout: TextIO | None = None,
) -> int:
    """Run the ACP server loop on stdio until EOF or session/close."""
    stdin = stdin if stdin is not None else sys.stdin
    stdout = stdout if stdout is not None else sys.stdout
    sessions: dict[str, Path] = {}

    while True:
        msg = _read(stdin)
        if msg is None:
            return 0
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") if isinstance(msg.get("params"), dict) else {}

        if method == "initialize":
            if mid is None:
                continue
            _write(
                stdout,
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {
                        "protocolVersion": 1,
                        "agentCapabilities": {},
                        "agentInfo": {
                            "name": _AGENT_NAME,
                            "title": "Ravand",
                            "version": _AGENT_VERSION,
                        },
                    },
                },
            )
            continue

        if method == "session/new":
            if mid is None:
                continue
            cwd_raw = params.get("cwd")
            if not cwd_raw:
                _write(
                    stdout,
                    {
                        "jsonrpc": "2.0",
                        "id": mid,
                        "error": {"code": -32602, "message": "cwd required"},
                    },
                )
                continue
            cwd = Path(str(cwd_raw)).resolve()
            session_id = str(uuid.uuid4())
            sessions[session_id] = cwd
            _write(
                stdout,
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {"sessionId": session_id},
                },
            )
            continue

        if method == "session/prompt":
            if mid is None:
                continue
            session_id = str(params.get("sessionId") or "")
            cwd = sessions.get(session_id)
            if cwd is None:
                _write(
                    stdout,
                    {
                        "jsonrpc": "2.0",
                        "id": mid,
                        "error": {"code": -32602, "message": "unknown session"},
                    },
                )
                continue
            prompt = _prompt_text(params)
            if not prompt:
                _write(
                    stdout,
                    {
                        "jsonrpc": "2.0",
                        "id": mid,
                        "error": {"code": -32602, "message": "prompt required"},
                    },
                )
                continue
            try:
                policy = resolve(cwd)
            except (PolicyDenied, UnknownAgent) as exc:
                audit_agent_denied(str(exc), cwd=cwd)
                _write(
                    stdout,
                    {"jsonrpc": "2.0", "id": mid, "error": _policy_error(exc)},
                )
                continue

            def acp_forward(update_msg: dict[str, Any]) -> None:
                fwd_params = dict(update_msg.get("params") or {})
                fwd_params["sessionId"] = session_id
                _write(
                    stdout,
                    {
                        "jsonrpc": "2.0",
                        "method": "session/update",
                        "params": fwd_params,
                    },
                )

            exit_code = run_prompt(
                policy,
                prompt,
                cwd=cwd,
                sink=lambda _event: None,
                yes=True,
                acp_forward=acp_forward,
            )
            stop = "end_turn" if exit_code == 0 else "error"
            _write(
                stdout,
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {"stopReason": stop},
                },
            )
            continue

        if method == "session/close":
            sid = str(params.get("sessionId") or "")
            sessions.pop(sid, None)
            if mid is not None:
                _write(stdout, {"jsonrpc": "2.0", "id": mid, "result": {}})
            return 0

        if mid is not None:
            _write(stdout, {"jsonrpc": "2.0", "id": mid, "result": {}})
