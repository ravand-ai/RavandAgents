"""Tests for the tool.pre hook runner (ravand_hooks)."""

from __future__ import annotations

import sys

import pytest

from ravand_hooks import run_tool_pre


def _script(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_allow_script_exits_zero(tmp_path):
    assert run_tool_pre(_script("pass"), tmp_path, {}) == "allow"


def test_deny_script_exits_nonzero(tmp_path):
    assert run_tool_pre(_script("import sys; sys.exit(1)"), tmp_path, {}) == "deny"


def test_missing_command_denies(tmp_path):
    result = run_tool_pre(
        ["definitely-not-an-executable-94-hooks-pre"], tmp_path, {}
    )
    assert result == "deny"


@pytest.mark.parametrize(
    "key,value",
    [
        ("OPENAI_API_KEY", "sk-abc123"),
        ("XAI_WHATEVER", "xai-abc123"),
        ("AUTH_HEADER", "Bearer abc123"),
        ("MY_TOKEN", "plain"),
        ("MY_SECRET", "plain"),
        ("HOOK_SECRET_NAME", "plain"),
    ],
)
def test_secrets_not_in_child_env(tmp_path, key, value):
    # Child exits 0 only if the secret key is absent from its environment.
    code = (
        "import os, sys; "
        f"sys.exit(1 if {key!r} in os.environ else 0)"
    )
    assert run_tool_pre(_script(code), tmp_path, {key: value}) == "allow"


def test_non_secret_env_is_passed(tmp_path):
    code = (
        "import os, sys; "
        "sys.exit(0 if os.environ.get('RAVAND_HOOK_TEST') == 'visible' else 1)"
    )
    assert (
        run_tool_pre(_script(code), tmp_path, {"RAVAND_HOOK_TEST": "visible"})
        == "allow"
    )
