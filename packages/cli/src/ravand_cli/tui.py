"""Grok-like operator TUI: chat transcript, composer, permission card."""

from __future__ import annotations

import sys
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.widgets import Footer, Log, Static, TextArea

from ravand_cli.status import header_text
from ravand_policy import PolicyDenied, UnknownAgent, resolve
from ravand_runtime import audit_agent_denied, run_prompt

Runner = Callable[..., int]


class Turn(Static):
    """One chat bubble. Mouse-selectable."""

    ALLOW_SELECT = True

    def __init__(self, role: str, text: str = "") -> None:
        super().__init__(text, classes=f"turn turn-{role}")
        self._buf = text

    def append(self, text: str) -> None:
        self._buf += text
        self.update(self._buf)

    @property
    def body(self) -> str:
        return self._buf


class RavandApp(App[int]):
    """Chat-style operator screen over run_prompt. Not a coding TUI."""

    TITLE = "ravand"
    ALLOW_SELECT = True
    CSS = """
    Screen {
        layout: vertical;
        background: #16141a;
        color: #e8e4ef;
    }
    #brand {
        dock: top;
        height: 3;
        padding: 0 2;
        background: #1e1b24;
        color: #e879f9;
        text-style: bold;
    }
    #status {
        height: 1;
        padding: 0 2;
        color: #a89bb5;
        background: #1e1b24;
    }
    #transcript {
        height: 1fr;
        padding: 1 2;
        scrollbar-gutter: stable;
    }
    .turn {
        width: 100%;
        margin: 0 0 1 0;
        padding: 1 2;
    }
    .turn-user {
        background: #2a2433;
        border-left: thick #e879f9;
        color: #f3eef8;
    }
    .turn-agent {
        background: #1c1a22;
        border-left: thick #7c6bf0;
        color: #e8e4ef;
    }
    .turn-sys {
        background: #1a181c;
        color: #8a7e96;
        border-left: thick #4a4454;
    }
    .turn-think {
        background: #18161c;
        color: #8a7e96;
        border-left: thick #5c5470;
        text-style: italic;
    }
    #perm {
        height: auto;
        min-height: 3;
        padding: 1 2;
        background: #3a2a10;
        color: #ffe9a8;
        border: tall #f5c542;
        display: none;
    }
    #composer {
        dock: bottom;
        height: 9;
        background: #1e1b24;
        padding: 0 1 1 1;
    }
    #prompt {
        height: 6;
        background: #16141a;
        border: tall #e879f9;
        color: #e8e4ef;
    }
    #hint {
        height: 1;
        color: #6f6578;
        padding: 0 1;
    }
    #stream { display: none; height: 0; }
    Footer { background: #1e1b24; }
    """

    BINDINGS = [
        Binding("ctrl+c", "interrupt", "Stop", priority=True),
        Binding("ctrl+shift+c", "copy_text", "Copy", priority=True),
        Binding("ctrl+y", "copy_text", "Copy", show=False),
        Binding("ctrl+j", "submit_prompt", "Send", priority=True),
        Binding("ctrl+enter", "submit_prompt", "Send", priority=True, show=False),
        Binding("ctrl+i", "submit_prompt", "Send", priority=True, show=False),
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
        self._elapsed = 0
        self._activity = ""
        self._quit_armed = False
        self._cancel = threading.Event()
        self._agent_turn: Turn | None = None
        self._think_turn: Turn | None = None
        self._base_header = ""
        self._think_buf = ""
        self._agent_buf = ""
        self._event_q: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def compose(self) -> ComposeResult:
        yield Static("ravand", id="brand")
        yield Static(id="status")
        yield VerticalScroll(id="transcript")
        yield Log(id="stream", highlight=False)
        yield Static(id="perm")
        with Vertical(id="composer"):
            yield Static(
                "enter newline  ·  ctrl+j send  ·  ctrl+shift+c copy  ·  y/n tools  ·  ctrl+c stop",
                id="hint",
            )
            yield TextArea(id="prompt")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_header(reprobe=True)
        self.set_interval(1.0, self._tick)
        self.set_interval(0.05, self._flush_pending)
        self.query_one("#transcript", VerticalScroll).mount(
            Turn("sys", "Operator console. Policy and audit stay on. Not a Grok clone.")
        )
        box = self.query_one("#prompt", TextArea)
        box.focus()

    def _tick(self) -> None:
        if not self._busy or not self.is_attached:
            return
        self._elapsed += 1
        try:
            self._refresh_header(running=True)
        except Exception:
            return

    def _refresh_header(self, *, running: bool = False, reprobe: bool = False) -> None:
        if not self.is_attached:
            return
        if reprobe or not self._base_header:
            self._base_header = header_text(self.cwd)
        line = self._base_header
        if running:
            action = self._activity or "working"
            line = f"running {self._elapsed}s  ·  {action}  ·  {line}"
        try:
            self.query_one("#status", Static).update(line)
            brand = f"ravand  ·  {self._activity or 'running…'}" if running else "ravand"
            self.query_one("#brand", Static).update(brand)
        except Exception:
            return

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
        self._elapsed = 0
        self._activity = "working"
        self._quit_armed = False
        self._cancel.clear()
        box.disabled = True
        self._refresh_header(running=True)
        self.query_one("#transcript", VerticalScroll).mount(Turn("user", prompt))
        self._agent_turn = Turn("agent", "")
        self.query_one("#transcript", VerticalScroll).mount(self._agent_turn)
        self._run_agent(prompt)

    def action_copy_text(self) -> None:
        selected = ""
        try:
            selected = self.screen.get_selected_text() or ""
        except Exception:
            selected = ""
        if selected.strip():
            self.copy_to_clipboard(selected)
            self._write_sys("copied selection")
            return
        last = ""
        try:
            agents = list(self.query("#transcript .turn-agent"))
            if agents:
                last = agents[-1].body
            if not last.strip():
                thinks = list(self.query("#transcript .turn-think"))
                if thinks:
                    last = thinks[-1].body
        except Exception:
            last = ""
        if not last.strip():
            try:
                log = self.query_one("#stream", Log)
                last = "".join(str(line) for line in getattr(log, "lines", []))
            except Exception:
                last = ""
        if last.strip():
            self.copy_to_clipboard(last)
            self._write_sys("copied last reply")

    def action_quit(self) -> None:
        self.action_interrupt()

    def action_interrupt(self) -> None:
        if self._asking:
            self._finish_ask(False)
        if self._busy:
            self._cancel.set()
            self._activity = "stopping"
            self._quit_armed = True
            self._refresh_header(running=True)
            self._write_sys("stopping  ·  ctrl+c again to quit")
            return
        if self._quit_armed:
            self.exit(0)
            return
        self._quit_armed = True
        self._write_sys("ctrl+c again to quit")

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
        bar = self.query_one("#perm", Static)
        bar.display = False
        self.query_one("#transcript", VerticalScroll).mount(
            Turn("sys", f"tool {'allowed' if ok else 'denied'}")
        )
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
        bar.update(f"Allow tool?\n{detail}\n[y] allow    [n] deny")
        bar.display = True

    def _sink(self, event: dict[str, Any]) -> None:
        if event.get("type") == "permission.ask":
            self.call_from_thread(self._apply_event, event)
            return
        with self._lock:
            self._event_q.append(event)

    def _apply_event(self, event: dict[str, Any]) -> None:
        kind = event.get("type")
        if kind == "text.delta":
            self._think_turn = None
            text = str(event.get("text") or "")
            if text:
                self._agent_buf += text
        elif kind == "thinking.delta":
            text = str(event.get("text") or "")
            if text:
                self._activity = "thinking"
                self._think_buf += text
        elif kind == "tool.call":
            self._flush_pending()
            self._think_turn = None
            tool = str(event.get("tool") or "tool")
            self._activity = tool
            self._write_sys(f"▸ {tool}")
        elif kind == "tool.result":
            self._flush_pending()
            tool = str(event.get("tool") or "tool")
            status = str(event.get("status") or "done")
            mark = "✓" if status != "failed" else "✗"
            self._write_sys(f"{mark} {tool}")
        elif kind == "permission.ask":
            self._flush_pending()
            tool = str(event.get("tool") or "tool")
            self._activity = f"ask {tool}"
            self._write_sys(f"permission  ·  {tool}")
        elif kind == "run.ended":
            self._flush_pending()
            status = str(event.get("status") or "")
            self._write_sys(f"run {status}")

    def _flush_pending(self) -> None:
        if not self.is_attached:
            return
        with self._lock:
            batch, self._event_q = self._event_q, []
        for event in batch:
            self._apply_event(event)
        think, self._think_buf = self._think_buf, ""
        agent, self._agent_buf = self._agent_buf, ""
        if think:
            self._append_think(think)
        if agent:
            self._write_stream(agent)

    def _write_stream(self, text: str) -> None:
        if not self.is_attached:
            return
        try:
            self.query_one("#stream", Log).write(text)
            if self._agent_turn is not None and text:
                self._agent_turn.append(text)
                self.query_one("#transcript", VerticalScroll).scroll_end(animate=False)
        except Exception:
            return

    @work(thread=True)
    def _run_agent(self, prompt: str) -> None:
        try:
            policy = resolve(self.cwd)
        except PolicyDenied as exc:
            audit_agent_denied(str(exc), cwd=self.cwd)
            self.call_from_thread(self._write_sys, f"denied: {exc}")
            self.call_from_thread(self._idle)
            return
        except UnknownAgent as exc:
            self.call_from_thread(self._write_sys, str(exc))
            self.call_from_thread(self._idle)
            return
        self._runner(
            policy,
            prompt,
            cwd=self.cwd,
            sink=self._sink,
            ask=self._ask,
            yes=False,
            cancel=self._cancel,
        )
        self.call_from_thread(self._idle)

    def _append_think(self, text: str) -> None:
        if not self.is_attached:
            return
        try:
            if self._think_turn is None:
                self._think_turn = Turn("think", "thinking  ·  ")
                self.query_one("#transcript", VerticalScroll).mount(self._think_turn)
            self._think_turn.append(text)
            self.query_one("#stream", Log).write(text)
            self.query_one("#transcript", VerticalScroll).scroll_end(animate=False)
        except Exception:
            return

    def _write_sys(self, text: str) -> None:
        if not self.is_attached:
            return
        try:
            self.query_one("#transcript", VerticalScroll).mount(Turn("sys", text))
            self.query_one("#stream", Log).write(text)
            self.query_one("#transcript", VerticalScroll).scroll_end(animate=False)
        except Exception:
            return

    def _idle(self) -> None:
        self._busy = False
        self._activity = ""
        self._agent_turn = None
        self._think_turn = None
        if not self.is_attached:
            return
        try:
            box = self.query_one("#prompt", TextArea)
            box.disabled = False
            box.focus()
            self._flush_pending()
            self._refresh_header(running=False, reprobe=True)
        except Exception:
            return


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
