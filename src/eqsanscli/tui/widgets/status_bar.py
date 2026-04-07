from __future__ import annotations

import os
from typing import TYPE_CHECKING

from rich.text import Text
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState

LLM_CONTEXT_WINDOW = 128_000


class HeaderBar(Widget):
    DEFAULT_CSS = """
    HeaderBar {
        dock: top;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    """

    session_name: reactive[str] = reactive("default")
    ipts_label: reactive[str] = reactive("IPTS-")
    active_table: reactive[str] = reactive("default")
    table_rows: reactive[int] = reactive(0)
    output_dir: reactive[str] = reactive("")
    tokens_used: reactive[int] = reactive(0)

    def render(self) -> Text:
        width = self.size.width
        left = f" {self.session_name}  {self.ipts_label}  [{self.active_table}:{self.table_rows}]  {self.output_dir}"
        right = "EQSANS CLI"
        if self.tokens_used > 0:
            pct = min(100, self.tokens_used * 100 // LLM_CONTEXT_WINDOW)
            right = f"tokens:{self.tokens_used:,} ({pct}%)  {right}"

        pad = width - len(left) - len(right)
        if pad < 1:
            pad = 1
        line = left + " " * pad + right
        return Text(line[:width])

    def update_from_state(self, state: SessionState) -> None:
        self.session_name = state.name
        self.ipts_label = f"IPTS-{state.ipts}" if state.ipts else "IPTS-"
        self.active_table = state.active_table
        self.table_rows = len(state.current_table.rows)
        self.output_dir = _short_path(os.path.abspath(state.output_directory))
        self.tokens_used = state.llm_tokens_used


_SPINNER_COLORS = ["cyan", "magenta", "yellow", "green", "blue", "red"]
_SPINNER_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class FooterBar(Widget):
    DEFAULT_CSS = """
    FooterBar {
        dock: bottom;
        height: 1;
        background: $primary;
        color: $text;
        padding: 0 1;
    }
    """

    llm_status: reactive[str] = reactive("")
    model_name: reactive[str] = reactive("")
    drtsans_label: reactive[str] = reactive("drtsans")
    _thinking: bool = False
    _job_running: bool = False
    _frame: int = 0
    _timer = None

    def render(self) -> Text:
        width = self.size.width

        if self._job_running:
            right = "^Q Quit  ^L Clear  [bold red]^X Cancel Job[/bold red]  ESC Focus  /help Commands"
            right_plain = "^Q Quit  ^L Clear  ^X Cancel Job  ESC Focus  /help Commands"
        else:
            right = "^Q Quit  ^L Clear  ESC Focus  /help Commands"
            right_plain = right

        result = Text()
        if self._thinking:
            frame = _SPINNER_FRAMES[self._frame % len(_SPINNER_FRAMES)]
            color = _SPINNER_COLORS[self._frame % len(_SPINNER_COLORS)]
            result.append(f" {frame} LLM thinking... ", style=f"bold {color}")
        elif self.model_name:
            result.append(f" LLM: {self.model_name} ")
        else:
            result.append(" LLM: not configured ")
        result.append(f" {self.drtsans_label} ", style="dim")

        if self._job_running:
            cancel_label = " ✕ Cancel "
            center_pad_left = (width - result.cell_len - len(cancel_label) - len(right_plain)) // 2
            if center_pad_left < 1:
                center_pad_left = 1
            result.append(" " * center_pad_left)
            result.append(cancel_label, style="bold red on dark_red")
            pad = width - result.cell_len - len(right_plain)
        else:
            pad = width - result.cell_len - len(right_plain)

        if pad < 0:
            pad = 0
        result.append(" " * pad)
        result.append_text(Text.from_markup(right))
        return result

    def set_job_running(self, running: bool) -> None:
        self._job_running = running
        self.refresh()

    def set_llm_thinking(self) -> None:
        self._thinking = True
        self._frame = 0
        if self._timer is None:
            self._timer = self.set_interval(0.1, self._tick)

    def set_llm_idle(self) -> None:
        self._thinking = False
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.refresh()

    def _tick(self) -> None:
        if self._thinking:
            self._frame += 1
            self.refresh()

    def update_model(self) -> None:
        from eqsanscli.config.settings import AppSettings
        settings = AppSettings.load()
        if settings.llm.is_configured:
            self.model_name = settings.llm.model
        else:
            self.model_name = ""

    def on_click(self, event) -> None:
        if self._job_running:
            app = self.app
            if hasattr(app, "cancel_job"):
                app.cancel_job()


def _short_path(path: str) -> str:
    if not path:
        return ""
    home = os.path.expanduser("~")
    if path.startswith(home):
        return "~" + path[len(home):]
    if len(path) > 40:
        return "..." + path[-37:]
    return path
