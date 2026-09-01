"""ravand tui: operator screen. Non-TTY must refuse. Textual app is interactive."""

from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _ravand(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["TERM"] = "dumb"
    return subprocess.run(
        ["uv", "run", "ravand", *args],
        cwd=ROOT,
        env=env,
        input=stdin,
        capture_output=True,
        text=True,
        check=False,
    )


def test_tui_non_tty_exits_nonzero() -> None:
    result = _ravand("tui")
    assert result.returncode != 0
    blob = (result.stdout + result.stderr).lower()
    assert "tty" in blob
    assert "jsonl" in blob


def test_help_lists_tui() -> None:
    result = _ravand("--help")
    assert result.returncode == 0
    assert "tui" in (result.stdout + result.stderr).lower()


def test_textual_app_streams_fake_run() -> None:
    from ravand_cli.tui import RavandApp

    seen: list[str] = []

    def fake_runner(policy, prompt, *, cwd, sink, ask, yes):
        seen.append(prompt)
        sink({"type": "text.delta", "text": "hello-tui"})
        sink({"type": "run.ended", "status": "ok"})
        return 0

    app = RavandApp(cwd=ROOT, runner=fake_runner)

    captured: dict[str, str] = {}

    async def _go() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            box = app.query_one("#prompt")
            box.load_text("say hi\nsecond line")
            app.action_submit_prompt()
            await pilot.pause(0.2)
            log = app.query_one("#stream")
            captured["text"] = "".join(str(line) for line in getattr(log, "lines", []))

    asyncio.run(_go())
    assert seen == ["say hi\nsecond line"]
    assert "hello-tui" in captured.get("text", "")


def test_textual_app_permission_y_allows() -> None:
    from ravand_cli.tui import RavandApp

    allowed: list[bool] = []

    def fake_runner(policy, prompt, *, cwd, sink, ask, yes):
        allowed.append(bool(ask) and ask("Fetch: https://example.com"))
        if allowed[-1]:
            sink({"type": "text.delta", "text": "fetched-ok"})
        sink({"type": "run.ended", "status": "ok"})
        return 0

    app = RavandApp(cwd=ROOT, runner=fake_runner)

    async def _go() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            box = app.query_one("#prompt")
            box.load_text("fetch")
            app.action_submit_prompt()
            await pilot.pause(0.2)
            await pilot.press("y")
            await pilot.pause(0.2)

    asyncio.run(_go())
    assert allowed == [True]


def test_textual_app_shows_user_bubble() -> None:
    from ravand_cli.tui import RavandApp, Turn

    def fake_runner(policy, prompt, *, cwd, sink, ask, yes):
        sink({"type": "text.delta", "text": "ok"})
        sink({"type": "run.ended", "status": "ok"})
        return 0

    app = RavandApp(cwd=ROOT, runner=fake_runner)
    roles: list[str] = []

    async def _go() -> None:
        async with app.run_test() as pilot:
            await pilot.pause()
            box = app.query_one("#prompt")
            box.load_text("hello you")
            app.action_submit_prompt()
            await pilot.pause(0.2)
            for child in app.query_one("#transcript").children:
                if isinstance(child, Turn):
                    roles.extend(child.classes)

    asyncio.run(_go())
    assert "turn-user" in roles
    assert "turn-agent" in roles


def test_textual_app_shows_tool_progress() -> None:
    from ravand_cli.tui import RavandApp, Turn

    def fake_runner(policy, prompt, *, cwd, sink, ask, yes):
        sink({"type": "thinking.delta", "text": "planning the reply"})
        sink({"type": "tool.call", "tool": "Read AGENTS.md", "status": "in_progress"})
        sink({"type": "tool.result", "tool": "Read AGENTS.md", "status": "completed"})
        sink({"type": "text.delta", "text": "hello-tui"})
        sink({"type": "run.ended", "status": "ok"})
        return 0

    app = RavandApp(cwd=ROOT, runner=fake_runner)
    blob = ""

    async def _go() -> None:
        nonlocal blob
        async with app.run_test() as pilot:
            await pilot.pause()
            box = app.query_one("#prompt")
            box.load_text("progress")
            app.action_submit_prompt()
            for _ in range(40):
                await pilot.pause(0.05)
                parts = []
                for child in app.query_one("#transcript").children:
                    if isinstance(child, Turn):
                        parts.append(child.body)
                blob = "\n".join(parts)
                if "Read AGENTS.md" in blob and "thinking" in blob.lower():
                    break

    asyncio.run(_go())
    assert "Read AGENTS.md" in blob
    assert "thinking" in blob.lower()
