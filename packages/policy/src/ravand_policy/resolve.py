"""Resolve harness.toml + user config into a policy. Fail closed."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from ravand_policy.errors import PolicyDenied, UnknownAgent


def ravand_home() -> Path:
    override = os.environ.get("RAVAND_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".ravand"


@dataclass
class ResolvedPolicy:
    profile: str
    home: str
    default_agent: str
    overflow_agent: str | None
    deny: list[str]
    permissions: str
    classification: str
    command: list[str]
    mcp: list[dict] = field(default_factory=list)
    agent: str = ""


def _load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _user_config(home: Path) -> dict:
    path = home / "config.toml"
    if not path.is_file():
        return {}
    return _load_toml(path)


def resolve(
    cwd: Path,
    *,
    profile_override: str | None = None,
    agent_override: str | None = None,
) -> ResolvedPolicy:
    cwd = cwd.resolve()
    harness_path = cwd / "harness.toml"
    home_root = ravand_home()
    user = _user_config(home_root)

    if harness_path.is_file():
        harness = _load_toml(harness_path)
    else:
        default_profile = user.get("default_profile", "personal")
        harness = {
            "profile": default_profile,
            "default": "",
            "overflow": "",
            "deny": [],
            "permissions": "repo-only",
            "classification": "internal",
            "agents": {},
        }

    repo_profile = str(harness.get("profile", "personal"))
    profile = profile_override or repo_profile
    classification = str(harness.get("classification", "internal"))
    deny = [str(x) for x in harness.get("deny", [])]
    permissions = str(harness.get("permissions", "repo-only"))
    default_agent = str(harness.get("default", ""))
    overflow_raw = str(harness.get("overflow") or "")
    overflow_agent = overflow_raw or None
    agents = harness.get("agents") or {}
    if not isinstance(agents, dict):
        raise PolicyDenied("harness agents table is invalid")

    if profile_override and profile_override != repo_profile:
        raise PolicyDenied(
            f"profile override {profile_override!r} does not match repo {repo_profile!r}"
        )
    if classification == "customer" and profile == "personal":
        raise PolicyDenied("customer classification cannot use personal profile")

    agent = agent_override or default_agent
    if not agent:
        raise UnknownAgent("no default agent")
    if agent in deny:
        raise PolicyDenied(f"agent {agent!r} is denied")
    if agent not in agents:
        raise UnknownAgent(f"unknown agent {agent!r}")

    profiles = user.get("profiles") or {}
    if isinstance(profiles, dict) and profile in profiles:
        allow = profiles[profile].get("allow")
        if isinstance(allow, list) and agent not in allow:
            raise PolicyDenied(f"agent {agent!r} is not allowed on profile {profile!r}")

    spec = agents[agent]
    if not isinstance(spec, dict) or "command" not in spec:
        raise UnknownAgent(f"agent {agent!r} has no command")
    command = [str(x) for x in spec["command"]]

    profile_home = home_root / "profiles" / profile
    return ResolvedPolicy(
        profile=profile,
        home=str(profile_home),
        default_agent=default_agent,
        overflow_agent=overflow_agent,
        deny=deny,
        permissions=permissions,
        classification=classification,
        command=command,
        agent=agent,
    )
