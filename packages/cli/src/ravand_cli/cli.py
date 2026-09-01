"""ravand CLI. Slice 0: help works. Other commands are not implemented."""

from __future__ import annotations

import argparse
import sys

NOT_IMPLEMENTED = "not implemented"


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ravand")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("which", help="resolve agent and profile for cwd")
    sub.add_parser("run", help="spawn the selected ACP agent")
    sub.add_parser("login", help="print vendor login hints")
    sub.add_parser("status", help="login doctor")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    print(NOT_IMPLEMENTED, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
