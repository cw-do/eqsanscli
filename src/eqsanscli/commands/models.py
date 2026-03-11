from __future__ import annotations

from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.config.settings import AppSettings

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState

AVAILABLE_MODELS = [
    "openai/gpt-5-mini",
    "google/gemini-3-flash-preview",
    "anthropic/claude-opus-4.6",
    "openai/gpt-4o",
]


async def handle_models(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        settings = AppSettings.load()
        current = settings.llm.model
        lines = ["Available LLM models:"]
        for m in AVAILABLE_MODELS:
            marker = "[bold cyan]●[/bold cyan]" if m == current else " "
            lines.append(f"  {marker} {m}")
        lines.append(f"\nCurrent: [bold]{current}[/bold]")
        lines.append("[dim]Usage: /models <name> to switch[/dim]")
        return CommandResult(success=True, message="\n".join(lines))

    choice = args[0].strip()
    matched = None
    for m in AVAILABLE_MODELS:
        if choice.lower() == m.lower() or choice.lower() in m.lower():
            matched = m
            break

    if not matched:
        return CommandResult(
            success=False,
            message=f"Unknown model: {choice}\nAvailable: {', '.join(AVAILABLE_MODELS)}",
        )

    import os
    os.environ["OPENROUTER_MODEL"] = matched

    return CommandResult(
        success=True,
        message=f"Switched to: [bold]{matched}[/bold]",
        data={"type": "model_changed", "model": matched},
    )
