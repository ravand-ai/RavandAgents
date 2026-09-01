"""TTY / forced human permission. Fail closed on timeout, EOF, or anything but y."""

from __future__ import annotations

import os
import sys
from typing import TextIO


def should_ask(*, yes: bool, is_tty: bool) -> bool:
    if yes:
        return False
    if os.environ.get("RAVAND_ASK") == "1":
        return True
    return is_tty


def confirm_permission(
    detail: str,
    *,
    stdin: TextIO | None = None,
    stderr: TextIO | None = None,
    timeout_sec: float = 60.0,
) -> bool:
    """Return True only for y/yes. Empty, n, EOF, timeout → False."""
    in_stream = stdin if stdin is not None else sys.stdin
    err_stream = stderr if stderr is not None else sys.stderr
    print(f"allow {detail}? [y/N]", file=err_stream, flush=True)
    try:
        fd = in_stream.fileno()
    except (AttributeError, OSError, ValueError):
        fd = None
    if fd is not None:
        import select

        ready, _, _ = select.select([fd], [], [], timeout_sec)
        if not ready:
            print("permission timeout: deny", file=err_stream, flush=True)
            return False
    line = in_stream.readline()
    if not line:
        return False
    return line.strip().lower() in {"y", "yes"}
