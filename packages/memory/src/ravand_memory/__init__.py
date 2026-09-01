"""File memory store. Isolation scope in every key. No cross-scope merge."""

from __future__ import annotations

import json
import re
from pathlib import Path

ISOLATIONS = frozenset({"session", "profile", "project"})
_SCOPE_KEY_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_TOKEN_MARKERS = ("sk-", "xai-", "Bearer")
_COOKIE_MARKERS = ("cookies", ".grok/", ".kimi/", ".cursor/", ".claude")


class FailClosed(Exception):
    """Memory could not allow the action."""


class FileStore:
    """Write notes under <root>/memory/<isolation>/<scope_key>/."""

    def __init__(
        self,
        root: Path | str,
        isolation: str,
        scope_key: str,
    ) -> None:
        if isolation not in ISOLATIONS:
            raise FailClosed(f"unknown memory isolation: {isolation!r}")
        if scope_key in {".", ".."} or not _SCOPE_KEY_RE.fullmatch(scope_key):
            raise FailClosed(f"invalid memory scope_key: {scope_key!r}")
        self._root = Path(root)
        self._isolation = isolation
        self._scope_key = scope_key

    def _scope_dir(self) -> Path:
        root = (self._root / "memory").resolve()
        path = (root / self._isolation / self._scope_key).resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise FailClosed("memory path escaped isolation") from exc
        return path

    def _notes_path(self) -> Path:
        directory = self._scope_dir()
        path = (directory / "notes.jsonl").resolve()
        try:
            path.relative_to(directory)
        except ValueError as exc:
            raise FailClosed("memory path escaped isolation") from exc
        return path

    def _refuse_secrets(self, text: str) -> None:
        for marker in _TOKEN_MARKERS:
            if marker in text:
                raise FailClosed("memory refuses tokens")
        lowered = text.lower()
        for marker in _COOKIE_MARKERS:
            if marker in lowered:
                raise FailClosed("memory refuses cookie paths")

    def write(self, note: str) -> None:
        if not isinstance(note, str):
            raise FailClosed("memory note must be text")
        self._refuse_secrets(note)
        payload = json.dumps({"text": note}, separators=(",", ":")) + "\n"
        self._refuse_secrets(payload)
        directory = self._scope_dir()
        directory.mkdir(parents=True, exist_ok=True)
        path = self._notes_path()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(payload)

    def read(self) -> list[str]:
        path = self._notes_path()
        if not path.is_file():
            return []
        notes: list[str] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            data = json.loads(line)
            text = str(data.get("text", ""))
            if text:
                notes.append(text)
        return notes


__all__ = ["FailClosed", "FileStore"]
