from __future__ import annotations

import os
from pathlib import Path

from rich.text import Text
from textual.events import Key
from textual.message import Message
from textual.widgets import TextArea

_FILE_COMMANDS = {"plot", "cat", "head", "tail", "ls", "cd", "cp", "mv", "rm", "load", "save"}


class CommandSubmitted(Message):
    def __init__(self, value: str) -> None:
        self.value = value
        super().__init__()


class CompletionHint(Message):
    def __init__(self, options: list[str]) -> None:
        self.options = options
        super().__init__()


class CompletableInput(TextArea):

    def __init__(self, placeholder: str = "", **kwargs) -> None:
        super().__init__(**kwargs)
        self._completions: list[str] = []
        self._tab_matches: list[str] = []
        self._tab_index: int = 0
        self._tab_prefix: str | None = None
        self._history: list[str] = []
        self._history_index: int = -1
        self._current_input: str = ""

    def on_mount(self) -> None:
        self.show_line_numbers = False

    async def _on_key(self, event: Key) -> None:
        if event.key == "enter":
            text = self.text.strip()
            if text:
                self._history.append(text)
                self._history_index = -1
                self._current_input = ""
                self.post_message(CommandSubmitted(text))
            self.clear()
            self._reset_tab()
            event.prevent_default()
            event.stop()
            return

        if event.key == "up":
            self._history_up()
            event.prevent_default()
            event.stop()
            return

        if event.key == "down":
            self._history_down()
            event.prevent_default()
            event.stop()
            return

        if event.key == "tab" and self.text:
            self._handle_tab()
            event.prevent_default()
            event.stop()
            return

        if event.key != "tab":
            self._reset_tab()

        await super()._on_key(event)

    def _history_up(self) -> None:
        if not self._history:
            return
        if self._history_index == -1:
            self._current_input = self.text
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        self.clear()
        self.insert(self._history[self._history_index])

    def _history_down(self) -> None:
        if self._history_index == -1:
            return
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self.clear()
            self.insert(self._history[self._history_index])
        else:
            self._history_index = -1
            self.clear()
            self.insert(self._current_input)

    def _handle_tab(self) -> None:
        current_text = self.text

        if self._tab_matches and self._tab_prefix is not None:
            self._tab_index = (self._tab_index + 1) % len(self._tab_matches)
            match = self._tab_matches[self._tab_index]
            full = f"{self._tab_prefix} {match}" if self._tab_prefix else match
            self.clear()
            self.insert(full)
            self.post_message(CompletionHint(self._tab_matches))
            return

        parts = current_text.split()
        if not parts:
            return
        
        last_token = parts[-1]
        prefix = " ".join(parts[:-1])

        if self._should_complete_path(parts):
            matches = self._get_path_completions(last_token)
            if matches:
                self._apply_completions(matches, prefix, last_token)
                return

        matches = [
            c for c in self._completions
            if c.lower().startswith(last_token.lower()) and c.lower() != last_token.lower()
        ]

        if matches:
            self._apply_completions(matches, prefix, last_token)

    def _should_complete_path(self, parts: list[str]) -> bool:
        if len(parts) < 2:
            return False
        cmd = parts[0].lower().lstrip("/")
        if cmd in _FILE_COMMANDS:
            return True
        if len(parts) >= 2 and parts[0].lower() == "/list" and parts[1].lower() in ("iq", "iqxqy"):
            return len(parts) > 2
        return False

    def _get_path_completions(self, partial: str) -> list[str]:
        try:
            partial_path = Path(partial).expanduser()
            
            if partial.endswith("/") or partial_path.is_dir():
                search_dir = partial_path if partial_path.is_dir() else partial_path.parent
                search_prefix = "" if partial.endswith("/") or partial_path.is_dir() else partial_path.name
            else:
                search_dir = partial_path.parent if partial_path.parent.exists() else Path(".")
                search_prefix = partial_path.name

            if not search_dir.exists():
                return []

            matches = []
            for entry in search_dir.iterdir():
                if entry.name.startswith(".") and not search_prefix.startswith("."):
                    continue
                if entry.name.lower().startswith(search_prefix.lower()):
                    if entry.is_dir():
                        matches.append(str(entry) + "/")
                    else:
                        matches.append(str(entry))
            
            return sorted(matches, key=lambda x: (not x.endswith("/"), x.lower()))[:20]
        except Exception:
            return []

    def _apply_completions(self, matches: list[str], prefix: str, last_token: str) -> None:
        if not matches:
            return
            
        if len(matches) == 1:
            full = f"{prefix} {matches[0]}" if prefix else matches[0]
            self.clear()
            self.insert(full)
            self._reset_tab()
            return

        self._tab_matches = matches
        self._tab_index = 0
        self._tab_prefix = prefix
        full = f"{prefix} {matches[0]}" if prefix else matches[0]
        self.clear()
        self.insert(full)
        self.post_message(CompletionHint(matches))

    def _reset_tab(self) -> None:
        self._tab_matches = []
        self._tab_index = 0
        self._tab_prefix = None

    def update_completions(self, completions: list[str]) -> None:
        self._completions = completions
