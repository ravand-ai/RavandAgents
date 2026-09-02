"""Cloud users, roles, per-project access. Fail closed."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path

from ravand_policy.errors import PolicyDenied
from ravand_policy.resolve import ravand_home

_TOKEN_MARKERS = ("sk-", "xai-", "Bearer")
_COOKIE_MARKERS = ("cookie", ".grok/", ".kimi/", ".cursor/", ".claude")


@dataclass(frozen=True)
class ProjectAccess:
    user: str
    role: str
    project: str
    profiles: list[str]
    accounts: list[str]


def _refuse_secrets(text: str) -> None:
    if any(marker in text for marker in _TOKEN_MARKERS):
        raise PolicyDenied("users config refuses tokens")
    lowered = text.lower()
    for marker in _COOKIE_MARKERS:
        if marker in lowered:
            raise PolicyDenied("users config refuses cookies")


def _scan(value: object) -> None:
    if isinstance(value, str):
        _refuse_secrets(value)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise PolicyDenied("users config keys must be strings")
            _refuse_secrets(key)
            _scan(item)
        return
    if isinstance(value, list):
        for item in value:
            _scan(item)


def _load_toml(path: Path) -> dict:
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise PolicyDenied("users config is invalid")
    return data


def _source(home: Path) -> dict:
    users_path = home / "users.toml"
    if users_path.is_file():
        data = _load_toml(users_path)
        _scan(data)
        return data
    config_path = home / "config.toml"
    if config_path.is_file():
        data = _load_toml(config_path)
        _scan(data)
        return data
    raise PolicyDenied("users config is missing")


def _string_list(raw: object, field: str) -> list[str]:
    if not isinstance(raw, list):
        raise PolicyDenied(f"{field} must be a list")
    parsed: list[str] = []
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise PolicyDenied(f"{field} entries must be strings")
        parsed.append(item)
    return parsed


def _parse_user(user_id: str, record: object) -> tuple[str, list[str] | None]:
    if not isinstance(record, dict):
        raise PolicyDenied(f"user {user_id!r} is invalid")
    role = record.get("role")
    if not isinstance(role, str) or not role.strip():
        raise PolicyDenied(f"user {user_id!r} role cannot be resolved")
    projects: list[str] | None = None
    if "projects" in record:
        projects = _string_list(record.get("projects"), "user projects")
    return role, projects


def _parse_role(role_id: str, record: object) -> tuple[list[str], list[str], list[str]]:
    if not isinstance(record, dict):
        raise PolicyDenied(f"role {role_id!r} is invalid")
    projects = _string_list(record.get("projects"), "role projects")
    profiles = _string_list(record.get("profiles"), "role profiles")
    accounts = _string_list(record.get("accounts"), "role accounts")
    if not projects:
        raise PolicyDenied(f"role {role_id!r} has no projects")
    return projects, profiles, accounts


def resolve_access(
    user_id: str,
    project: str,
    *,
    home: Path | None = None,
) -> ProjectAccess:
    """Resolve a user role on a project. Fail closed if the role is unknown."""
    if not isinstance(user_id, str) or not user_id.strip():
        raise PolicyDenied("user id is invalid")
    if not isinstance(project, str) or not project.strip():
        raise PolicyDenied("project id is invalid")
    root = Path(home) if home is not None else ravand_home()
    data = _source(root)
    users = data.get("users")
    if not isinstance(users, dict):
        raise PolicyDenied("users table is invalid")
    roles = data.get("roles")
    if not isinstance(roles, dict):
        raise PolicyDenied("roles table is invalid")
    if user_id not in users:
        raise PolicyDenied(f"unknown user {user_id!r}")
    role_id, user_projects = _parse_user(user_id, users[user_id])
    if role_id not in roles:
        raise PolicyDenied(f"unknown role {role_id!r}")
    role_projects, profiles, accounts = _parse_role(role_id, roles[role_id])
    if user_projects is None:
        allowed = role_projects
    else:
        allowed = [item for item in user_projects if item in role_projects]
    if project not in allowed:
        raise PolicyDenied(
            f"user {user_id!r} cannot access project {project!r}"
        )
    return ProjectAccess(
        user=user_id,
        role=role_id,
        project=project,
        profiles=list(profiles),
        accounts=list(accounts),
    )
