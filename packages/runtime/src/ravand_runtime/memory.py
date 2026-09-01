"""Parse harness.toml [memory] and open FileStore. Fail closed."""

from __future__ import annotations

import hashlib
import tomllib
from dataclasses import dataclass
from pathlib import Path

from ravand_memory import FailClosed, FileStore
from ravand_policy import ResolvedPolicy

_SUPPORTED_ISOLATIONS = frozenset({"session", "profile", "project"})


@dataclass(frozen=True)
class MemoryConfig:
    isolation: str
    store: str


def load_memory_config(cwd: Path) -> MemoryConfig | None:
    path = cwd / "harness.toml"
    if not path.is_file():
        return None
    with path.open("rb") as handle:
        harness = tomllib.load(handle)
    memory = harness.get("memory")
    if memory is None:
        return None
    if not isinstance(memory, dict):
        raise FailClosed("harness memory table is invalid")
    isolation = str(memory.get("isolation", "")).strip()
    store = str(memory.get("store", "")).strip()
    if not isolation or not store:
        raise FailClosed("harness memory isolation and store are required")
    return MemoryConfig(isolation=isolation, store=store)


def _scope_key(
    config: MemoryConfig,
    policy: ResolvedPolicy,
    cwd: Path,
    task_id: str,
) -> str:
    if config.isolation == "session":
        return task_id
    if config.isolation == "profile":
        return policy.profile
    if config.isolation == "project":
        digest = hashlib.sha256(str(cwd.resolve()).encode()).hexdigest()[:16]
        return digest
    raise FailClosed(f"unknown memory isolation: {config.isolation!r}")


def open_file_store(
    config: MemoryConfig,
    policy: ResolvedPolicy,
    *,
    root: Path,
    cwd: Path,
    task_id: str,
) -> FileStore:
    if config.store != "file":
        raise FailClosed(f"unknown memory store: {config.store!r}")
    if config.isolation not in _SUPPORTED_ISOLATIONS:
        raise FailClosed(f"unknown memory isolation: {config.isolation!r}")
    scope_key = _scope_key(config, policy, cwd, task_id)
    return FileStore(root, isolation=config.isolation, scope_key=scope_key)


def augment_prompt(prompt: str, notes: list[str]) -> str:
    if not notes:
        return prompt
    return "[memory]\n" + "\n".join(notes) + "\n\n" + prompt
