"""NOTE.md — per-outputdir reproducibility log.

Records commands the user runs and explicit `/note add` entries with timestamps.
The file lives at `{state.output_directory}/NOTE.md` so each experiment travels
with its own log.
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


NOTE_FILENAME = "NOTE.md"

# Commands NOT auto-logged (read-only views, settings, the note command itself, etc.)
_LOG_DENYLIST = {
    "show", "list", "help", "settings", "note", "clear", "exit", "quit",
    "history", "model", "fast",
}

_HEADER_TEMPLATE = """# eqsanscli session log

Created: {created}

This NOTE.md is an automatic log of commands run with eqsanscli, plus any
manual notes added via `/note add "..."`. Replaying the listed commands in
order should reproduce the data reduction workflow recorded here.

Format: each entry is timestamped (HH:MM:SS). Lines starting with `>` are
commands; lines starting with `**NOTE**` are user-authored annotations.

---

"""


def note_path(state: SessionState) -> str:
    """Return the absolute path of NOTE.md for the current output directory."""
    return os.path.abspath(os.path.join(state.output_directory, NOTE_FILENAME))


def _ensure_note_file(path: str) -> None:
    """Create NOTE.md with header if it doesn't exist."""
    if os.path.exists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    created = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(path, "w") as f:
        f.write(_HEADER_TEMPLATE.format(created=created))


def _today_header() -> str:
    return datetime.now().strftime("## %Y-%m-%d\n")


def _append_with_day_header(path: str, line: str) -> None:
    """Append a line, inserting a `## YYYY-MM-DD` header on day boundaries."""
    today = _today_header()
    needs_header = True
    if os.path.exists(path):
        with open(path, "r") as f:
            content = f.read()
        if today in content:
            # Find the last day header and check if it's today
            last_day_idx = content.rfind("\n## ")
            if last_day_idx >= 0:
                last_header_line = content[last_day_idx + 1 :].split("\n", 1)[0]
                if last_header_line == today.rstrip("\n"):
                    needs_header = False

    with open(path, "a") as f:
        if needs_header:
            f.write("\n" + today + "\n")
        f.write(line)
        if not line.endswith("\n"):
            f.write("\n")


def append_user_note(state: SessionState, text: str) -> str:
    """Add a manual note. Returns the path."""
    path = note_path(state)
    _ensure_note_file(path)
    ts = datetime.now().strftime("%H:%M:%S")
    ipts_tag = f" [IPTS-{state.ipts}]" if state.ipts else ""
    line = f"- {ts}{ipts_tag}  **NOTE:** {text}"
    _append_with_day_header(path, line)
    return path


def maybe_log_command(state: SessionState, cmd_name: str, full_command: str) -> None:
    """Auto-log a command if it's not in the denylist. Silent on failure."""
    if cmd_name in _LOG_DENYLIST:
        return
    try:
        path = note_path(state)
        _ensure_note_file(path)
        ts = datetime.now().strftime("%H:%M:%S")
        ipts_tag = f" [IPTS-{state.ipts}]" if state.ipts else ""
        line = f"- {ts}{ipts_tag}  `> {full_command}`"
        _append_with_day_header(path, line)
    except Exception:
        # Never let logging break dispatch
        pass


def read_note(state: SessionState) -> str | None:
    """Return NOTE.md contents, or None if missing."""
    path = note_path(state)
    if not os.path.exists(path):
        return None
    with open(path, "r") as f:
        return f.read()


def tail_note(state: SessionState, n_lines: int) -> str | None:
    """Return the last `n_lines` non-empty entries of NOTE.md, or None if missing."""
    content = read_note(state)
    if content is None:
        return None
    lines = [ln for ln in content.splitlines() if ln.strip()]
    return "\n".join(lines[-n_lines:])
