"""Test plumbing for security contract tests (issue #1).

Only touches sys.path so the workspace packages under test
(``ravand_policy``, ``ravand_permissions``, ``ravand_runtime``) are
importable even when they are not yet wired as install dependencies
of the CLI in the current slice. No PyPI dependencies are added.
"""

import sys
from pathlib import Path

PACKAGES = Path(__file__).resolve().parents[2] / "packages"
for name in ("policy", "permissions", "runtime"):
    src = PACKAGES / name / "src"
    if src.is_dir() and str(src) not in sys.path:
        sys.path.insert(0, str(src))
