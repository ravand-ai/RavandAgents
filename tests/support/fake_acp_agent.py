"""Minimal ACP agent for tests. NDJSON JSON-RPC over stdio."""

from __future__ import annotations

import json
import sys


def _read() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line)


def _write(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main() -> None:
    next_req = 1000
    while True:
        msg = _read()
        if msg is None:
            return
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") or {}
        if method == "initialize":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {
                        "protocolVersion": 1,
                        "agentCapabilities": {"loadSession": False},
                    },
                }
            )
        elif method == "session/new":
            _write({"jsonrpc": "2.0", "id": mid, "result": {"sessionId": "sess-test"}})
        elif method == "session/prompt":
            prompt = json.dumps(params)
            if "passwd" in prompt:
                req_id = next_req
                next_req += 1
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": req_id,
                        "method": "session/request_permission",
                        "params": {
                            "sessionId": params.get("sessionId"),
                            "toolCall": {
                                "toolCallId": "t1",
                                "title": "write",
                                "kind": "edit",
                                "rawInput": {"path": "/etc/passwd"},
                            },
                            "options": [
                                {
                                    "optionId": "allow",
                                    "name": "Allow",
                                    "kind": "allow_once",
                                },
                                {
                                    "optionId": "deny",
                                    "name": "Deny",
                                    "kind": "reject_once",
                                },
                            ],
                        },
                    }
                )
                _read()
                _write(
                    {"jsonrpc": "2.0", "id": mid, "result": {"stopReason": "end_turn"}}
                )
            else:
                _write(
                    {
                        "jsonrpc": "2.0",
                        "method": "session/update",
                        "params": {
                            "sessionId": params.get("sessionId"),
                            "update": {
                                "sessionUpdate": "agent_message_chunk",
                                "content": {"type": "text", "text": "hello-from-fake"},
                            },
                        },
                    }
                )
                _write(
                    {"jsonrpc": "2.0", "id": mid, "result": {"stopReason": "end_turn"}}
                )
        elif method == "session/close":
            if mid is not None:
                _write({"jsonrpc": "2.0", "id": mid, "result": {}})
            return
        elif mid is not None:
            _write({"jsonrpc": "2.0", "id": mid, "result": {}})


if __name__ == "__main__":
    main()
