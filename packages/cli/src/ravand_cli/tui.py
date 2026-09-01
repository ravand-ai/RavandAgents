"""Operator TUI (Textual). Multi-line prompt, streamed log, y/n permission."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import Footer, Log, Static, TextArea

from ravand_cli.status import header_text
from ravand_policy import PolicyDenied, UnknownAgent, resolve
from ravand_runtime import audit_agent_denied, run_prompt

Runner = Callable[..., int]


class RavandApp(App[int]):
    """Interactive operator screen over run_prompt."""

    CSS = """
    Screen { layout: vertical; }
    #status { height: 3; padding: 0 1; background: $primary; color: $text; }
    #stream { height: 1fr; border: solid $surface; }
    #perm { height: 3; padding: 0 1; background: $warning; color: $text; display: none; }
    #prompt { height: 8; border: solid $accent; }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+j", "submit_prompt", "Submit", priority=True),
    ]

    def __init__(
        self,
        cwd: Path,
        *,
        runner: Runner | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.cwd = cwd.resolve()
        self._runner = runner or run_prompt
        self._perm_event = threading.Event()
        self._perm_ok = False
        self._asking = False
        self._busy = False

    def compose(self) -> ComposeResult:
        yield Static(id="status")
        yield Log(id="stream", highlight=False)
        yield Static(id="perm")
        yield TextArea(id="prompt")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#status", Static).update(header_text(self.cwd))
        box = self.query_one("#prompt", TextArea)
        box.tooltip = "Enter = newline. Ctrl+J = run."
        box.focus()

    def action_submit_prompt(self) -> None:
        box = self.query_one("#prompt", TextArea)
        prompt = box.text.strip()
        if not prompt or self._busy or self._asking:
            return
        if prompt in {"q", "quit", "exit"}:
            self.exit(0)
            return
        box.load_text("")
        self._busy = True
        box.disabled = True
        self._run_agent(prompt)

    def on_key(self, event) -> None:  # noqa: ANN001
        if not self._asking:
            return
        key = getattr(event, "key", "")
        if key in {"y", "Y"}:
            self._finish_ask(True)
            event.stop()
        elif key in {"n", "N"}:
            self._finish_ask(False)
            event.stop()

    def _finish_ask(self, ok: bool) -> None:
        self._perm_ok = ok
        self._asking = False
        self.query_one("#perm", Static).display = False
        self._perm_event.set()

    def _ask(self, detail: str) -> bool:
        self._perm_event.clear()
        self._perm_ok = False
        self.call_from_thread(self._show_ask, detail)
        self._perm_event.wait()
        return self._perm_ok

    def _show_ask(self, detail: str) -> None:
        self._asking = True
        bar = self.query_one("#perm", Static)
        bar.update(f"allow {detail}?  y / n")
        bar.display = True

    def _sink(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "text.delta":
            text = str(event.get("text") or "")
            if text:
                self.call_from_thread(self._write_stream, text)
        elif kind == "run.ended":
            status = str(event.get("status") or "")
            self.call_from_thread(self._write_stream, f"\n[{status}]\n")

    def _write_stream(self, text: str) -> None:
        self.query_one("#stream", Log).write(text)

    @work(thread=True)
    def _run_agent(self, prompt: str) -> None:
        try:
            policy = resolve(self.cwd)
        except PolicyDenied as exc:
            audit_agent_denied(str(exc), cwd=self.cwd)
            self.call_from_thread(self._write_stream, f"denied: {exc}\n")
            self.call_from_thread(self._idle)
            return
        except UnknownAgent as exc:
            self.call_from_thread(self._write_stream, f"{exc}\n")
            self.call_from_thread(self._idle)
            return
        self._runner(
            policy,
            prompt,
            cwd=self.cwd,
            sink=self._sink,
            ask=self._ask,
            yes=False,
        )
        self.call_from_thread(self._idle)

    def _idle(self) -> None:
        self._busy = False
        box = self.query_one("#prompt", TextArea)
        box.disabled = False
        box.focus()
        try:
            self.query_one("#status", Static).update(header_text(self.cwd))
        except Exception:
            pass


def run_tui(cwd: Path) -> int:
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print(
            "ravand tui needs a TTY. Use: ravand run --format jsonl",
            file=sys.stderr,
        )
        return 2
    app = RavandApp(cwd.resolve())
    result = app.run()
    return 0 if result is None else int(result)
