"""Command input widget — docked at bottom, accepts commands and natural language."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.message import Message
from textual.widget import Widget
from textual.widgets import Input, Static
from textual.containers import Horizontal


class CommandSubmitted(Message):
    """Emitted when the user presses Enter in the command input."""

    def __init__(self, value: str) -> None:
        self.value = value
        super().__init__()


class CommandInput(Widget):
    """Bottom-docked command input bar with prompt."""

    DEFAULT_CSS = """
    CommandInput {
        dock: bottom;
        height: 3;
        padding: 0 1;
        background: $surface;
        border-top: solid $primary;
    }
    CommandInput Horizontal {
        height: 1;
        margin-top: 1;
    }
    CommandInput .prompt-label {
        width: auto;
        color: $accent;
        padding-right: 1;
    }
    CommandInput #cmd-input {
        width: 1fr;
        border: none;
        background: $surface;
    }
    """

    def __init__(self) -> None:
        super().__init__()
        self._history: list[str] = []
        self._history_index: int = -1

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static("eqsans> ", classes="prompt-label")
            yield Input(
                placeholder="Type a command or ask in natural language...",
                id="cmd-input",
            )

    def on_mount(self) -> None:
        """Focus the input widget on mount."""
        self.query_one("#cmd-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle Enter key in the input."""
        value = event.value.strip()
        if value:
            self._history.append(value)
            self._history_index = -1
            self.post_message(CommandSubmitted(value))
        event.input.value = ""
        # Re-focus the input after submission
        event.input.focus()
