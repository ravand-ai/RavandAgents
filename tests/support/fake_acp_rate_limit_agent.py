"""ACP agent that fails session/prompt with rate_limit for overflow tests."""

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
                    "result": {"sessionId": "sess-rate-limit"},
                }
            )
        elif method == "session/prompt":
            _write(
                {
                    "jsonrpc": "2.0",
                    "id": mid,
                    "error": {"code": 429, "message": "rate_limit exceeded"},
                }
            )
        elif method == "session/close":
            if mid is not None:
                _write({"jsonrpc": "2.0", "id": mid, "result": {}})
            return
        elif mid is not None:
            _write({"jsonrpc": "2.0", "id": mid, "result": {}})


if __name__ == "__main__":
    main()
