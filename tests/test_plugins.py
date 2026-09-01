"""Plugin host: load a disk package (GitHub issue #108)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

from ravand_plugins import (
    FailClosed,
    PluginHost,
    PluginManifest,
    add_plugin,
    list_plugins,
    load_plugin,
)

ROOT = Path(__file__).resolve().parents[1]

KNOWN_KIND = "integration"
FORBIDDEN_KINDS = ("policy", "permissions")


def _write_toml_manifest(
    directory: Path,
    *,
    id: str = "acme.jira",
    version: str = "1.0.0",
    kind: str = KNOWN_KIND,
    inject: list[str] | None = None,
    grants: dict[str, bool] | None = None,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    inject = inject if inject is not None else ["policy"]
    grants = grants if grants is not None else {kind: True}
    grants_lines = "\n".join(f"{key} = {str(value).lower()}" for key, value in grants.items())
    text = "\n".join(
        [
            f'id = "{id}"',
            f'version = "{version}"',
            f'kind = "{kind}"',
            f"inject = {json.dumps(inject)}",
            "",
            "[grants]",
            grants_lines,
            "",
        ]
    )
    path = directory / "plugin.toml"
    path.write_text(text, encoding="utf-8")
    return path


def _write_json_manifest(
    directory: Path,
    *,
    id: str = "acme.slack",
    version: str = "0.1.0",
    kind: str = "hook",
    inject: list[str] | None = None,
    grants: dict[str, bool] | None = None,
) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    inject = inject if inject is not None else []
    grants = grants if grants is not None else {kind: True}
    payload = {
        "id": id,
        "version": version,
        "kind": kind,
        "inject": inject,
        "grants": grants,
    }
    path = directory / "plugin.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_load_plugin_toml_manifest(tmp_path: Path) -> None:
    pkg = tmp_path / "jira"
    _write_toml_manifest(pkg)
    manifest = load_plugin(pkg)
    assert manifest.id == "acme.jira"
    assert manifest.version == "1.0.0"
    assert manifest.kind == KNOWN_KIND
    assert manifest.inject == ["policy"]
    assert manifest.grants == {KNOWN_KIND: True}
    assert manifest.path == pkg.resolve()


def test_load_plugin_json_manifest(tmp_path: Path) -> None:
    pkg = tmp_path / "slack"
    _write_json_manifest(pkg)
    manifest = load_plugin(pkg)
    assert manifest.id == "acme.slack"
    assert manifest.kind == "hook"
    assert manifest.grants == {"hook": True}


def test_unknown_kind_fails_closed(tmp_path: Path) -> None:
    pkg = tmp_path / "bad"
    _write_toml_manifest(pkg, kind="not-a-real-kind", grants={"not-a-real-kind": True})
    with pytest.raises(FailClosed, match="unknown plugin kind"):
        load_plugin(pkg)


@pytest.mark.parametrize("kind", FORBIDDEN_KINDS)
def test_forbidden_kind_fails_closed(tmp_path: Path, kind: str) -> None:
    pkg = tmp_path / kind
    _write_toml_manifest(pkg, id=f"evil.{kind}", kind=kind, grants={kind: True})
    with pytest.raises(FailClosed, match="cannot replace kernel"):
        load_plugin(pkg)


def test_missing_manifest_fails_closed(tmp_path: Path) -> None:
    pkg = tmp_path / "empty"
    pkg.mkdir()
    with pytest.raises(FailClosed, match="manifest"):
        load_plugin(pkg)


def test_missing_required_field_fails_closed(tmp_path: Path) -> None:
    pkg = tmp_path / "partial"
    pkg.mkdir()
    (pkg / "plugin.toml").write_text('version = "1.0.0"\n', encoding="utf-8")
    with pytest.raises(FailClosed, match="id"):
        load_plugin(pkg)


def test_add_and_list_plugins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "ravand-home"
    monkeypatch.setenv("RAVAND_HOME", str(home))
    source = tmp_path / "src"
    _write_toml_manifest(source, id="demo.integration")
    host = PluginHost(home)
    manifest = host.add(source)
    assert manifest.id == "demo.integration"
    listed = host.list()
    assert len(listed) == 1
    assert listed[0].id == "demo.integration"
    assert listed[0].kind == KNOWN_KIND
    assert (home / "plugins" / "demo.integration" / "plugin.toml").is_file()


def test_add_plugin_module_api(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "ravand-home"
    monkeypatch.setenv("RAVAND_HOME", str(home))
    source = tmp_path / "pkg"
    _write_json_manifest(source, id="demo.hook", kind="hook")
    manifest = add_plugin(source, home)
    assert isinstance(manifest, PluginManifest)
    assert manifest.id == "demo.hook"
    plugins = list_plugins(home)
    assert [p.id for p in plugins] == ["demo.hook"]


def test_ravand_plugin_list_cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "ravand-home"
    monkeypatch.setenv("RAVAND_HOME", str(home))
    source = tmp_path / "src"
    _write_toml_manifest(source, id="cli.demo")
    env = os.environ.copy()
    env["RAVAND_HOME"] = str(home)
    add_result = subprocess.run(
        ["uv", "run", "ravand", "plugin", "add", str(source)],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert add_result.returncode == 0, add_result.stderr
    list_result = subprocess.run(
        ["uv", "run", "ravand", "plugin", "list"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert list_result.returncode == 0, list_result.stderr
    rows = json.loads(list_result.stdout)
    assert len(rows) == 1
    assert rows[0]["id"] == "cli.demo"
    assert rows[0]["kind"] == KNOWN_KIND
