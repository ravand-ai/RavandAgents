"""ravand status login doctor. Probes vendor login without reading cookie contents."""

from __future__ import annotations

import shutil
import tomllib
from pathlib import Path

from ravand_policy import PolicyDenied, UnknownAgent, resolve
from ravand_profile import ensure_profile_home

# Relative to profile HOME. Stat only; never open for read.
# Grok CLI login writes auth.json, not cookies.
_COOKIE_MARKERS: dict[str, tuple[str, ...]] = {
    "grok": (".grok", "auth.json"),
    "kimi": (".kimi", "credentials"),
    "cursor": (".cursor",),
    "claude": (".claude",),
}
_GH_MARKER = (".config", "gh", "hosts.yml")


def _load_harness(cwd: Path) -> dict:
    path = cwd / "harness.toml"
    if not path.is_file():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _classification_denied(harness: dict) -> str | None:
    profile = str(harness.get("profile", "personal"))
    classification = str(harness.get("classification", "internal"))
    if classification == "customer" and profile == "personal":
        return "customer classification cannot use personal profile"
    return None


def _cookie_login(profile_home: Path, parts: tuple[str, ...]) -> str:
    path = profile_home.joinpath(*parts)
    try:
        if path.is_file():
            return "logged-in" if path.stat().st_size > 0 else "missing"
        if path.is_dir():
            for child in path.iterdir():
                try:
                    if child.is_file() and child.stat().st_size > 0:
                        return "logged-in"
                except OSError:
                    continue
            return "missing"
    except OSError:
        return "missing"
    return "missing"


def _cli_on_path(command: list[str]) -> bool:
    return bool(command) and shutil.which(command[0]) is not None


def _probe_login(agent_id: str, command: list[str], profile_home: Path) -> str:
    marker = _COOKIE_MARKERS.get(agent_id)
    if marker is not None:
        state = _cookie_login(profile_home, marker)
        if state == "logged-in":
            return state
        if not _cli_on_path(command):
            return "unknown"
        return "missing"
    if not _cli_on_path(command):
        return "unknown"
    return "missing"


def _agent_roles(
    agent_id: str,
    *,
    default_agent: str,
    overflow_agent: str,
) -> list[str]:
    roles: list[str] = []
    if agent_id == default_agent:
        roles.append("default")
    if overflow_agent and agent_id == overflow_agent:
        roles.append("overflow")
    if agent_id != default_agent and agent_id != overflow_agent:
        roles.append("registered")
    return roles


def header_text(cwd: Path) -> str:
    """One-line status for the TUI. Never reads cookie file contents."""
    cwd = cwd.resolve()
    harness = _load_harness(cwd)
    deny_reason = _classification_denied(harness)
    if deny_reason is not None:
        return f"denied: {deny_reason}"
    try:
        policy = resolve(cwd)
    except PolicyDenied as exc:
        return f"denied: {exc}"
    except UnknownAgent as exc:
        return str(exc)
    ensure_profile_home(policy.home)
    parts = [
        f"profile {policy.profile}",
        f"default {policy.default_agent}",
    ]
    if policy.overflow_agent:
        parts.append(f"overflow {policy.overflow_agent}")
    parts.append(policy.permissions)
    agents = harness.get("agents") or {}
    if isinstance(agents, dict):
        home = Path(policy.home)
        bits = []
        for agent_id in sorted(agents):
            spec = agents[agent_id]
            if not isinstance(spec, dict):
                continue
            command = [str(part) for part in spec.get("command", [])]
            bits.append(f"{agent_id}={_probe_login(agent_id, command, home)}")
        if bits:
            parts.append(" ".join(bits))
    return "  ".join(parts)


def run_status(cwd: Path) -> int:
    cwd = cwd.resolve()
    harness = _load_harness(cwd)
    deny_reason = _classification_denied(harness)
    if deny_reason is not None:
        profile = str(harness.get("profile", "personal"))
        print(f"profile {profile}")
        print(f"denied: {deny_reason}")
        return 0

    try:
        policy = resolve(cwd)
    except PolicyDenied as exc:
        print("denied")
        print(str(exc))
        return 0
    except UnknownAgent as exc:
        print(str(exc))
        return exc.exit_code

    ensure_profile_home(policy.home)
    profile_home = Path(policy.home)
    agents = harness.get("agents") or {}
    if not isinstance(agents, dict):
        agents = {}

    default_agent = policy.default_agent
    overflow_agent = policy.overflow_agent or ""

    print(f"profile {policy.profile}")
    print(f"home {policy.home}")
    print(f"default {default_agent}")
    if overflow_agent:
        print(f"overflow {overflow_agent}")

    for agent_id in sorted(agents):
        spec = agents[agent_id]
        if not isinstance(spec, dict):
            continue
        command = [str(part) for part in spec.get("command", [])]
        login = _probe_login(agent_id, command, profile_home)
        roles = _agent_roles(
            agent_id,
            default_agent=default_agent,
            overflow_agent=overflow_agent,
        )
        suffix = f" ({', '.join(roles)})" if roles else ""
        print(f"{agent_id}{suffix}: {login}")

    print(f"gh: {_cookie_login(profile_home, _GH_MARKER)}")
    return 0
