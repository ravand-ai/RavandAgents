"""Policy store seam. Fail closed when unreachable."""

from __future__ import annotations

import os
import tomllib
from pathlib import Path

from ravand_policy.errors import FailClosed


class FilePolicyStore:
    """Read harness.toml and user config from disk."""

    def require_reachable(self, *, home: Path, cwd: Path) -> None:
        try:
            (home / "config.toml").exists()
            (cwd / "harness.toml").exists()
        except OSError as exc:
            raise FailClosed("policy unreachable") from exc

    def load_toml(self, path: Path) -> dict:
        try:
            with path.open("rb") as handle:
                return tomllib.load(handle)
        except OSError as exc:
            raise FailClosed("policy unreachable") from exc

    def user_config(self, home: Path) -> dict:
        path = home / "config.toml"
        try:
            present = path.is_file()
        except OSError as exc:
            raise FailClosed("policy unreachable") from exc
        if not present:
            return {}
        return self.load_toml(path)


class DownPolicyStore:
    """Test / injected store that cannot be reached. Soft-deny forbidden."""

    def require_reachable(self, *, home: Path, cwd: Path) -> None:
        raise FailClosed("policy unreachable")

    def load_toml(self, path: Path) -> dict:
        raise FailClosed("policy unreachable")

    def user_config(self, home: Path) -> dict:
        raise FailClosed("policy unreachable")


def default_policy_store() -> FilePolicyStore | DownPolicyStore:
    """Pick store from RAVAND_POLICY_STORE (down) or file."""
    flag = os.environ.get("RAVAND_POLICY_STORE", "").strip().lower()
    if flag == "down":
        return DownPolicyStore()
    return FilePolicyStore()
