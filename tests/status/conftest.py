"""Fixtures for status doctor tests. Does not open vendor cookie files."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def isolated_home(tmp_path: Path) -> Path:
    """HOME that cannot see the developer's real ~/.ravand or cookie stores."""
    home = tmp_path / "home"
    home.mkdir()
    return home
