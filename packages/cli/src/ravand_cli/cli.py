"""ravand CLI."""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path

from ravand_policy import FailClosed, PolicyDenied, UnknownAgent, resolve
from ravand_profile import ensure_profile_home
from ravand_registry import login_hint
from ravand_cli.ask import confirm_permission, confirm_plan, should_ask
from ravand_cli.pause import require_not_paused, set_pause
from ravand_cli.status import run_status
from ravand_cli.tui import run_tui
from ravand_plugins import FailClosed as PluginFailClosed, PluginHost
from ravand_runtime import audit_agent_denied, run_native_prompt, run_prompt, serve_acp, steer_prompt
from ravand_runtime.cron import serve_cron
from ravand_runtime.http_api import DEFAULT_HTTP_PORT, serve_http
from ravand_runtime.plan import plan_mode_active
from ravand_runtime.serve import serve_all
from ravand_runtime.worker import serve_worker

NOT_IMPLEMENTED = "not implemented"


def _print_run_event(event: dict, *, fmt: str) -> None:
    if fmt != "text":
        print(json.dumps(event), flush=True)
        return
    etype = str(event.get("type") or "")
    if etype in {"text.delta", "thinking.delta"}:
        print(str(event.get("text") or ""), end="", flush=True)
        return
    if etype in {"tool.call", "tool.result"}:
        tool = event.get("tool") or "tool"
        print(f"\n[{tool}]", flush=True)
        return
    if etype == "run.started":
        print("run started", flush=True)
        return
    if etype == "run.ended":
        status = event.get("status") or ""
        print(f"\nrun ended {status}", flush=True)
        return


def _harness_template() -> str:
    bundled = Path(__file__).resolve().parent / "harness.toml"
    if bundled.is_file():
        return bundled.read_text(encoding="utf-8")
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "examples" / "harness.toml"
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    raise FileNotFoundError("harness.toml template is missing")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ravand")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("init", help="write ./harness.toml")
    which = sub.add_parser("which", help="resolve agent and profile for cwd")
    which.add_argument("--profile", dest="profile_override")
    which.add_argument("-a", "--agent", dest="agent_override")
    which.add_argument("--account", dest="account_override")
    run = sub.add_parser("run", help="spawn the selected ACP agent")
    run.add_argument("prompt", nargs="?")
    run.add_argument("-a", "--agent", dest="agent_override")
    run.add_argument("--account", dest="account_override")
    run.add_argument("--format", choices=["jsonl", "text"], default="jsonl")
    run.add_argument(
        "--yes",
        action="store_true",
        help="auto-decide permissions (repo-only); never prompt",
    )
    login = sub.add_parser("login", help="print vendor login hints")
    login.add_argument("profile", nargs="?", default=None)
    pause = sub.add_parser(
        "pause",
        help="fail-close new runs for an agent+profile pair",
    )
    pause.add_argument("--agent", required=True, dest="pause_agent")
    pause.add_argument("--profile", required=True, dest="pause_profile")
    sub.add_parser("status", help="login doctor")
    sub.add_parser("tui", help="operator screen (TTY)")
    steer = sub.add_parser("steer", help="continue a live session")
    steer.add_argument("session_id")
    steer.add_argument("text")
    plugin = sub.add_parser("plugin", help="manage disk plugins")
    plugin_sub = plugin.add_subparsers(dest="plugin_command")
    plugin_add = plugin_sub.add_parser("add", help="install a plugin from a path")
    plugin_add.add_argument("source", type=Path)
    plugin_sub.add_parser("list", help="list installed plugins")
    serve = sub.add_parser(
        "serve",
        help="http + cron + worker on one bus",
        description=(
            "With no subcommand, start http, cron, and worker on one Bus "
            "so webhook and cron enqueue is visible to the worker."
        ),
    )
    serve.add_argument(
        "--port",
        type=int,
        default=DEFAULT_HTTP_PORT,
        help=f"loopback port for http (default {DEFAULT_HTTP_PORT})",
    )
    serve_sub = serve.add_subparsers(dest="serve_command")
    serve_sub.add_parser("acp", help="stdio ACP server (agent ravand)")
    http = serve_sub.add_parser("http", help="local SSE HTTP gateway")
    http.add_argument(
        "--port",
        type=int,
        default=DEFAULT_HTTP_PORT,
        help=f"loopback port (default {DEFAULT_HTTP_PORT})",
    )
    serve_sub.add_parser("cron", help="local cron scheduler")
    serve_sub.add_parser("worker", help="consume q.tasks from the bus")
    return parser


def _init() -> int:
    dest = Path.cwd() / "harness.toml"
    if dest.exists():
        print("harness.toml already exists; refusing to overwrite", file=sys.stderr)
        return 3
    dest.write_text(_harness_template(), encoding="utf-8")
    return 0


def _which(args: argparse.Namespace) -> int:
    try:
        policy = resolve(
            Path.cwd(),
            profile_override=getattr(args, "profile_override", None),
            agent_override=getattr(args, "agent_override", None),
            account_override=getattr(args, "account_override", None),
        )
    except PolicyDenied as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except UnknownAgent as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except FailClosed as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    ensure_profile_home(policy.home)
    payload = {
        "profile": policy.profile,
        "agent": policy.agent,
        "account": policy.account,
        "kind": policy.account_kind,
        "overflow": policy.overflow_agent or "",
        "permissions": policy.permissions,
        "sandbox": policy.sandbox,
        "home": policy.home,
        "command": policy.command,
        "mcp": policy.mcp,
        "skillsAllow": policy.skills_allow,
        "functionsAllow": policy.functions_allow,
        "agentsMd": policy.agents_md,
        "loop": policy.loop,
        "auth": "unknown",
    }
    print(json.dumps(payload))
    return 0


def _run(args: argparse.Namespace) -> int:
    prompt = args.prompt
    if not prompt:
        print("prompt required", file=sys.stderr)
        return 2
    try:
        policy = resolve(
            Path.cwd(),
            agent_override=getattr(args, "agent_override", None),
            account_override=getattr(args, "account_override", None),
        )
    except PolicyDenied as exc:
        audit_agent_denied(str(exc), cwd=Path.cwd())
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except UnknownAgent as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except FailClosed as exc:
        audit_agent_denied(str(exc), cwd=Path.cwd())
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    try:
        require_not_paused(policy.agent, policy.profile)
    except PolicyDenied as exc:
        audit_agent_denied(str(exc), cwd=Path.cwd())
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    fmt = str(getattr(args, "format", "jsonl") or "jsonl")
    if policy.loop == "native":
        def sink(event: dict) -> None:
            _print_run_event(event, fmt=fmt)

        return run_native_prompt(
            policy,
            prompt,
            cwd=Path.cwd(),
            sink=sink,
        )
    if policy.account_kind == "api":
        denied = PolicyDenied(
            f"account {policy.account!r} kind api cannot spawn ACP"
        )
        audit_agent_denied(str(denied), cwd=Path.cwd())
        print(str(denied), file=sys.stderr)
        return denied.exit_code

    def sink(event: dict) -> None:
        _print_run_event(event, fmt=fmt)

    yes = bool(getattr(args, "yes", False))
    ask = None
    if should_ask(yes=yes, is_tty=sys.stdin.isatty()):
        ask = confirm_permission
    cwd = Path.cwd()
    ask_plan = confirm_plan if plan_mode_active(cwd, policy) else None
    return run_prompt(
        policy,
        prompt,
        cwd=cwd,
        sink=sink,
        ask=ask,
        ask_plan=ask_plan,
        yes=yes,
    )


def _steer(args: argparse.Namespace) -> int:
    def sink(event: dict) -> None:
        print(json.dumps(event), flush=True)

    return steer_prompt(args.session_id, args.text, sink=sink)


def _plugin_add(args: argparse.Namespace) -> int:
    host = PluginHost()
    try:
        manifest = host.add(args.source)
    except PluginFailClosed as exc:
        print(str(exc), file=sys.stderr)
        return 3
    print(json.dumps(manifest.to_dict()))
    return 0


def _plugin_list() -> int:
    host = PluginHost()
    rows = [manifest.to_dict() for manifest in host.list()]
    print(json.dumps(rows))
    return 0


def _login(args: argparse.Namespace) -> int:
    profile = args.profile
    try:
        policy = resolve(
            Path.cwd(),
            profile_override=profile if profile else None,
        )
    except PolicyDenied as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    except UnknownAgent as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    ensure_profile_home(policy.home)
    print(f"profile {policy.profile}")
    print(f"home {policy.home}")
    agent_ids: list[str] = []
    harness_path = Path.cwd() / "harness.toml"
    if harness_path.is_file():
        with harness_path.open("rb") as handle:
            harness = tomllib.load(handle)
        agents = harness.get("agents") or {}
        if isinstance(agents, dict):
            agent_ids = sorted(str(key) for key in agents)
    if not agent_ids:
        agent_ids = [policy.agent]
        if policy.overflow_agent and policy.overflow_agent not in agent_ids:
            agent_ids.append(policy.overflow_agent)
    for agent_id in agent_ids:
        print(f"HOME={policy.home} {login_hint(agent_id)}")
    print(f"HOME={policy.home} gh auth login")
    return 0


def _pause(args: argparse.Namespace) -> int:
    try:
        set_pause(args.pause_agent, args.pause_profile)
    except PolicyDenied as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.command is None:
        parser.print_help()
        return 0
    if args.command == "init":
        return _init()
    if args.command == "which":
        return _which(args)
    if args.command == "login":
        return _login(args)
    if args.command == "pause":
        return _pause(args)
    if args.command == "run":
        return _run(args)
    if args.command == "steer":
        return _steer(args)
    if args.command == "status":
        return run_status(Path.cwd())
    if args.command == "tui":
        return run_tui(Path.cwd())
    if args.command == "plugin":
        if args.plugin_command == "add":
            return _plugin_add(args)
        if args.plugin_command == "list":
            return _plugin_list()
        print(NOT_IMPLEMENTED, file=sys.stderr)
        return 2
    if args.command == "serve":
        if args.serve_command == "acp":
            return serve_acp()
        if args.serve_command == "http":
            return serve_http(port=int(args.port))
        if args.serve_command == "cron":
            return serve_cron()
        if args.serve_command == "worker":
            return serve_worker()
        if args.serve_command is None:
            return serve_all(port=int(args.port))
        print(NOT_IMPLEMENTED, file=sys.stderr)
        return 2
    print(NOT_IMPLEMENTED, file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
