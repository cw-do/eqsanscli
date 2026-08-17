"""Command router — dispatches raw input strings to command handlers.

Accepts both /commands and natural language. For Phase 1, only /commands
are handled directly. NL routing via LLM is added in Phase 6.
"""

from __future__ import annotations

import logging
import shlex
import textwrap
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Coroutine

_DEFAULT_WRAP_WIDTH = 100

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState

logger = logging.getLogger(__name__)


@dataclass
class CommandResult:
    """Result of executing a command."""

    success: bool
    message: str = ""
    data: Any = None  # optional structured data for TUI rendering


# Type alias for command handlers
# A handler receives (args: list[str], state: SessionState) and returns CommandResult
CommandHandler = Callable[[list[str], "SessionState"], Coroutine[Any, Any, CommandResult]]


class CommandRouter:
    """Routes input strings to registered command handlers.

    Design notes:
    - Accepts raw strings: both '/show 35520' and 'show me IPTS 35520'
    - /commands are dispatched directly via prefix matching
    - Non-/commands are reserved for LLM parsing (Phase 6)
    - Handlers are async to support long-running operations (reduction, ONCat fetch)
    """

    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}
        self._aliases: dict[str, str] = {}

    def register(self, command: str, handler: CommandHandler) -> None:
        """Register a handler for a /command.

        Args:
            command: The command name without slash, e.g., "show", "reduce"
            handler: Async callable(args, state) -> CommandResult
        """
        self._handlers[command] = handler

    def alias(self, alias_name: str, target_command: str) -> None:
        """Register an alias for an existing command."""
        self._aliases[alias_name] = target_command

    async def dispatch(self, raw_input: str, state: SessionState) -> CommandResult:
        """Route a raw input string to the appropriate handler.

        Dispatching logic:
        1. If input starts with '/', parse as command
        2. Otherwise, attempt NL parsing (Phase 6) or return unrecognized
        """
        text = raw_input.strip()
        if not text:
            return CommandResult(success=True)

        # Record in history
        state.add_to_history(text)

        if text.startswith("/"):
            return await self._dispatch_command(text[1:], state)

        return await self._dispatch_natural_language(text, state)

    async def _dispatch_command(self, text: str, state: SessionState) -> CommandResult:
        """Parse and dispatch a /command string."""
        try:
            parts = shlex.split(text)
        except ValueError as e:
            return CommandResult(success=False, message=f"Parse error: {e}")

        if not parts:
            return CommandResult(success=False, message="Empty command.")

        cmd_name = parts[0].lower()
        args = parts[1:]

        # Check aliases
        if cmd_name in self._aliases:
            cmd_name = self._aliases[cmd_name]

        # For compound commands like "show table", "set config", "export script"
        # try matching "cmd_name subcommand" first, then fall back to "cmd_name"
        result: CommandResult | None = None
        if args:
            compound = f"{cmd_name} {args[0].lower()}"
            if compound in self._handlers:
                handler = self._handlers[compound]
                result = await handler(args[1:], state)

        if result is None:
            if cmd_name in self._handlers:
                handler = self._handlers[cmd_name]
                result = await handler(args, state)
            else:
                return CommandResult(
                    success=False,
                    message=f"Unknown command: /{cmd_name}. Use /help to see available commands.",
                )

        # Auto-log successful commands to NOTE.md (best-effort, never break dispatch)
        if result.success:
            try:
                from eqsanscli.services.note_service import maybe_log_command
                maybe_log_command(state, cmd_name, f"/{text}")
            except Exception:
                pass

        return result

    async def _dispatch_natural_language(self, text: str, state: SessionState) -> CommandResult:
        from eqsanscli.services.llm_handler import parse_natural_language

        commands = await parse_natural_language(text, state)
        if not commands:
            return CommandResult(
                success=False,
                message="LLM not configured or unavailable. Use /help for commands, or prefix with /.",
            )

        has_commands = any(self._is_valid_command(c.strip()) for c in commands)
        if not has_commands:
            wrap_w = getattr(state, "wrap_width", _DEFAULT_WRAP_WIDTH)
            wrapped_lines: list[str] = []
            for line in "\n".join(commands).split("\n"):
                if len(line) <= wrap_w:
                    wrapped_lines.append(line)
                else:
                    wrapped_lines.extend(
                        textwrap.fill(line, width=wrap_w).split("\n")
                    )
            return CommandResult(
                success=True,
                message="\n".join(wrapped_lines),
            )

        results: list[str] = []
        all_ok = True
        last_data = None
        for cmd in commands:
            cmd = cmd.strip()
            if not self._is_valid_command(cmd):
                results.append(cmd)
                continue
            results.append(f"[dim]→ {cmd}[/dim]")
            result = await self._dispatch_command(cmd[1:], state)
            if result.message:
                results.append(result.message)
            if result.data:
                last_data = result.data
            if not result.success:
                all_ok = False
                break

        return CommandResult(
            success=all_ok,
            message="\n".join(results),
            data=last_data,
        )

    def _is_valid_command(self, text: str) -> bool:
        """Is `text` a /command this router can dispatch?

        Must accept compound registrations ("export script", "apply preset")
        the same way `_dispatch_command` does. Checking only the first word made
        the natural-language path silently swallow every command whose first
        word is not also registered bare: `/export script` and
        `/apply preset ...` were echoed back to the user as chat prose and never
        executed.
        """
        if not text.startswith("/"):
            return False
        parts = text[1:].split()
        if not parts:
            return False
        first = parts[0].lower()
        if first in self._handlers or first in self._aliases:
            return True
        if len(parts) >= 2 and f"{first} {parts[1].lower()}" in self._handlers:
            return True
        return False

    @property
    def commands(self) -> list[str]:
        """List all registered command names."""
        return sorted(self._handlers.keys())
