"""Minimal ACP agent for tests. NDJSON JSON-RPC over stdio.

FAKE_ACP_AUTH=required: advertise authMethods, fail authenticate (-32000).
FAKE_ACP_AUTH=cached: advertise authMethods, accept authenticate.
FAKE_ACP_STATE=<path>: mark the file if a session is spawned after a
failed authenticate handshake (must never happen).
"""

from __future__ import annotations

import json
import os
import sys

AUTH_MODE = os.environ.get("FAKE_ACP_AUTH", "")
STATE_PATH = os.environ.get("FAKE_ACP_STATE", "")

auth_failed = False


def _mark_spawn() -> None:
    if STATE_PATH:
        with open(STATE_PATH, "a", encoding="utf-8") as handle:
            handle.write("spawned-after-auth-failure\n")


def _read() -> dict | None:
    line = sys.stdin.readline()
    if not line:
        return None
    return json.loads(line)


def _write(msg: dict) -> None:
    sys.stdout.write(json.dumps(msg) + "\n")
    sys.stdout.flush()


def main() -> None:
    global auth_failed
    next_req = 1000
    while True:
        msg = _read()
        if msg is None:
            return
        method = msg.get("method")
        mid = msg.get("id")
        params = msg.get("params") or {}
        if method == "initialize":
            result: dict = {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": False},
            }
            if AUTH_MODE in {"required", "cached"}:
                result["authMethods"] = [
                    {"id": "cached_token", "name": "Cached token"}
                ]
            _write({"jsonrpc": "2.0", "id": mid, "result": result})
        elif method == "authenticate":
            if AUTH_MODE == "required":
                auth_failed = True
                _write(
                    {
                        "jsonrpc": "2.0",
                        "id": mid,
                        "error": {"code": -32000, "message": "Authentication required"},
                    }
                )
            else:
                _write({"jsonrpc": "2.0", "id": mid, "result": {}})
        elif method == "session/new":
            if auth_failed:
                _mark_spawn()
            _write({"jsonrpc": "2.0", "id": mid, "result": {"sessionId": "sess-test"}})
        elif method == "session/prompt":
            if auth_failed:
                _mark_spawn()
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
            elif "fetch" in prompt:
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
                                "toolCallId": "t-fetch",
                                "title": "Fetch: https://example.com",
                                "kind": "fetch",
                                "rawInput": {
                                    "variant": "WebFetch",
                                    "url": "https://example.com",
                                },
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
                reply = _read() or {}
                option = (
                    ((reply.get("result") or {}).get("outcome") or {}).get("optionId")
                )
                if option != "deny":
                    _write(
                        {
                            "jsonrpc": "2.0",
                            "method": "session/update",
                            "params": {
                                "sessionId": params.get("sessionId"),
                                "update": {
                                    "sessionUpdate": "agent_message_chunk",
                                    "content": [
                                        {"type": "text", "text": "fetched-ok"},
                                    ],
                                },
                            },
                        }
                    )
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
