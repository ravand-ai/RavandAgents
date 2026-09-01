"""Plugin host: load disk packages with manifest validation. Fail closed."""

from __future__ import annotations

import json
import os
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

KNOWN_KINDS = frozenset(
    {
        "function",
        "tool",
        "service",
        "loop",
        "sandbox",
        "bus",
        "memory",
        "account",
        "skill",
        "hook",
        "mcp",
        "trigger",
        "workflow",
        "pipeline",
        "integration",
        "eval",
    }
)

_FORBIDDEN_KINDS = frozenset({"policy", "permissions"})


class FailClosed(Exception):
    """Plugin host refused to load or install."""


@dataclass(frozen=True)
class PluginManifest:
    id: str
    version: str
    kind: str
    inject: list[str] = field(default_factory=list)
    grants: dict[str, bool] = field(default_factory=dict)
    path: Path | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "version": self.version,
            "kind": self.kind,
            "inject": list(self.inject),
            "grants": dict(self.grants),
        }
        if self.path is not None:
            payload["path"] = str(self.path)
        return payload


def ravand_home() -> Path:
    override = os.environ.get("RAVAND_HOME")
    if override:
        return Path(override).expanduser()
    return Path.home() / ".ravand"


def _require_str(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise FailClosed(f"plugin manifest missing {key!r}")
    return value.strip()


def _parse_inject(raw: object) -> list[str]:
    if raw is None:
        return []
    if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
        raise FailClosed("plugin manifest inject must be a list of strings")
    return list(raw)


def _parse_grants(raw: object) -> dict[str, bool]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise FailClosed("plugin manifest grants must be a table")
    grants: dict[str, bool] = {}
    for key, value in raw.items():
        if not isinstance(key, str):
            raise FailClosed("plugin manifest grants keys must be strings")
        if isinstance(value, bool):
            grants[key] = value
        else:
            raise FailClosed(f"plugin manifest grant {key!r} must be boolean")
    return grants


def _validate_kind(kind: str) -> None:
    if kind in _FORBIDDEN_KINDS:
        raise FailClosed("plugin cannot replace kernel law (policy or permissions)")
    if kind not in KNOWN_KINDS:
        raise FailClosed(f"unknown plugin kind: {kind!r}")


def _manifest_from_data(data: dict[str, object], *, path: Path) -> PluginManifest:
    plugin_id = _require_str(data, "id")
    version = _require_str(data, "version")
    kind = _require_str(data, "kind")
    _validate_kind(kind)
    return PluginManifest(
        id=plugin_id,
        version=version,
        kind=kind,
        inject=_parse_inject(data.get("inject")),
        grants=_parse_grants(data.get("grants")),
        path=path.resolve(),
    )


def _read_manifest_file(path: Path) -> dict[str, object]:
    if path.suffix == ".json":
        with path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        if not isinstance(data, dict):
            raise FailClosed("plugin manifest must be a JSON object")
        return data
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    return data


def load_plugin(directory: Path | str) -> PluginManifest:
    """Load and validate a plugin package from a directory."""
    root = Path(directory).resolve()
    if not root.is_dir():
        raise FailClosed(f"plugin path is not a directory: {root}")

    manifest_path: Path | None = None
    for name in ("plugin.toml", "plugin.json"):
        candidate = root / name
        if candidate.is_file():
            manifest_path = candidate
            break
    if manifest_path is None:
        raise FailClosed("plugin manifest not found (plugin.toml or plugin.json)")

    data = _read_manifest_file(manifest_path)
    return _manifest_from_data(data, path=root)


def _plugins_root(home: Path | None = None) -> Path:
    return (home or ravand_home()) / "plugins"


def add_plugin(source: Path | str, home: Path | None = None) -> PluginManifest:
    """Install a disk plugin under ~/.ravand/plugins/<id>/."""
    manifest = load_plugin(source)
    root = _plugins_root(home)
    target = root / manifest.id
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(Path(source).resolve(), target)
    return load_plugin(target)


def list_plugins(home: Path | None = None) -> list[PluginManifest]:
    """List installed plugins sorted by id."""
    root = _plugins_root(home)
    if not root.is_dir():
        return []
    manifests: list[PluginManifest] = []
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        try:
            manifests.append(load_plugin(entry))
        except FailClosed:
            continue
    return manifests


class PluginHost:
    """Manage installed plugins under a Ravand home directory."""

    def __init__(self, home: Path | str | None = None) -> None:
        self._home = Path(home).expanduser() if home is not None else ravand_home()

    def add(self, source: Path | str) -> PluginManifest:
        return add_plugin(source, self._home)

    def list(self) -> list[PluginManifest]:
        return list_plugins(self._home)


__all__ = [
    "FailClosed",
    "KNOWN_KINDS",
    "PluginHost",
    "PluginManifest",
    "add_plugin",
    "list_plugins",
    "load_plugin",
    "ravand_home",
]
