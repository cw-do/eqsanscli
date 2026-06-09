"""/note — per-outputdir reproducibility log."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.services.note_service import (
    append_user_note,
    note_path,
    read_note,
    tail_note,
)

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


_USAGE = (
    "Usage:\n"
    '  /note add "text"     — add a manual note (timestamped)\n'
    "  /note show [N]       — show last N entries (default 30)\n"
    "  /note path           — show the NOTE.md file path\n"
    "  /note clear          — delete NOTE.md (asks first)"
)


async def handle_note(args: list[str], state: SessionState) -> CommandResult:
    if not args or args[0] in ("--help", "-h", "help"):
        return CommandResult(success=False, message=_USAGE)

    sub = args[0].lower()

    if sub == "add":
        if len(args) < 2:
            return CommandResult(success=False, message='Usage: /note add "your note text"')
        text = " ".join(args[1:]).strip()
        if not text:
            return CommandResult(success=False, message="Note text is empty.")
        path = append_user_note(state, text)
        return CommandResult(success=True, message=f"Note added → {path}")

    if sub == "show":
        n = 30
        if len(args) >= 2:
            try:
                n = int(args[1])
            except ValueError:
                return CommandResult(success=False, message=f"Invalid line count: {args[1]}")
        tail = tail_note(state, n)
        if tail is None:
            return CommandResult(
                success=False,
                message=f"No NOTE.md yet at {note_path(state)}",
            )
        return CommandResult(
            success=True,
            message=f"[bold]{note_path(state)}[/bold] (last {n} entries):\n\n{tail}",
        )

    if sub == "path":
        path = note_path(state)
        exists = "exists" if os.path.exists(path) else "not yet created"
        return CommandResult(success=True, message=f"{path}  [dim]({exists})[/dim]")

    if sub == "clear":
        path = note_path(state)
        if not os.path.exists(path):
            return CommandResult(success=True, message=f"No NOTE.md at {path} — nothing to clear.")
        # Confirm via second arg `--yes` to avoid accidental loss
        if len(args) < 2 or args[1] != "--yes":
            return CommandResult(
                success=False,
                message=f"Will delete {path}.\nRe-run as: /note clear --yes",
            )
        os.unlink(path)
        return CommandResult(success=True, message=f"Deleted {path}")

    if sub == "full":
        content = read_note(state)
        if content is None:
            return CommandResult(success=False, message=f"No NOTE.md at {note_path(state)}")
        return CommandResult(success=True, message=content)

    return CommandResult(success=False, message=f"Unknown subcommand: {sub}\n\n{_USAGE}")
