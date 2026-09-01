"""ACP agent used as overflow fallback in tests."""

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
                    "result": {"protocolVersion": 1},
                }
            )
        elif method == "session/new":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "result": {"sessionId": "sess-overflow"},
                }
            )
        elif method == "session/prompt":
            _write(
                {
                    "jsonrpc": "2.0",
                    "method": "session/update",
                    "params": {
                        "sessionId": params.get("sessionId"),
                        "update": {
                            "sessionUpdate": "agent_message_chunk",
                            "content": {"type": "text", "text": "hello-from-overflow"},
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
