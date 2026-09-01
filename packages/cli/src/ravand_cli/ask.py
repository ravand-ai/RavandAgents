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


def _read_yes(
    prompt: str,
    *,
    stdin: TextIO | None = None,
    stderr: TextIO | None = None,
    timeout_sec: float | None = None,
    timeout_message: str = "permission timeout: deny",
) -> bool:
    """Return True only for y/yes. Empty, n, EOF, timeout → False."""
    in_stream = stdin if stdin is not None else sys.stdin
    err_stream = stderr if stderr is not None else sys.stderr
    print(prompt, file=err_stream, flush=True)
    if timeout_sec is not None:
        try:
            fd = in_stream.fileno()
        except (AttributeError, OSError, ValueError):
            fd = None
        if fd is not None:
            import select

            ready, _, _ = select.select([fd], [], [], timeout_sec)
            if not ready:
                print(timeout_message, file=err_stream, flush=True)
                return False
    line = in_stream.readline()
    if not line:
        return False
    return line.strip().lower() in {"y", "yes"}


def confirm_permission(
    detail: str,
    *,
    stdin: TextIO | None = None,
    stderr: TextIO | None = None,
    timeout_sec: float | None = None,
) -> bool:
    """Return True only for y/yes. Empty, n, EOF, timeout → False.

    Default waits forever. Pass timeout_sec only for tests that need a cap.
    """
    return _read_yes(
        f"allow {detail}? [y/N]",
        stdin=stdin,
        stderr=stderr,
        timeout_sec=timeout_sec,
    )


def confirm_plan(
    detail: str,
    *,
    stdin: TextIO | None = None,
    stderr: TextIO | None = None,
    timeout_sec: float | None = None,
) -> bool:
    """Approve or deny a plan. Fail closed on timeout, EOF, or anything but y."""
    if timeout_sec is None:
        raw = os.environ.get("RAVAND_PLAN_TIMEOUT", "").strip()
        if raw:
            timeout_sec = float(raw)
    return _read_yes(
        f"allow plan ({detail})? [y/N]",
        stdin=stdin,
        stderr=stderr,
        timeout_sec=timeout_sec,
        timeout_message="plan timeout: deny",
    )
