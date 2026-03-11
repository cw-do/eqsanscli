from __future__ import annotations

from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState

_VALID_SCALES = {"loglog", "linlin", "loglin", "linlog"}
_VALID_LINESTYLES = {"line", "marker", "line+marker"}


def _show_all(state: SessionState) -> str:
    scale = _scale_label(state.plot_logx, state.plot_logy)
    lines = [
        "[bold]Current settings:[/bold]",
        f"  textwrap     {state.wrap_width}",
        f"  figsize      {state.plot_figsize[0]} {state.plot_figsize[1]}",
        f"  dpi          {state.plot_dpi}",
        f"  plotscale    {scale}",
        f"  errorbars    {'on' if state.plot_errorbars else 'off'}",
        f"  linestyle    {state.plot_linestyle}",
    ]
    return "\n".join(lines)


def _scale_label(logx: bool, logy: bool) -> str:
    if logx and logy:
        return "loglog"
    if not logx and not logy:
        return "linlin"
    if logx and not logy:
        return "loglin"
    return "linlog"


async def handle_settings(args: list[str], state: SessionState) -> CommandResult:
    if not args or args[0].lower() == "show":
        return CommandResult(success=True, message=_show_all(state))

    sub = args[0].lower()

    if sub == "textwrap":
        if len(args) < 2:
            return CommandResult(
                success=True,
                message=f"textwrap = {state.wrap_width}\nUsage: /settings textwrap <width>  (40-200)",
            )
        try:
            width = int(args[1])
        except ValueError:
            return CommandResult(success=False, message=f"Invalid width: {args[1]} (must be integer)")
        if width < 40 or width > 200:
            return CommandResult(success=False, message=f"Width must be between 40 and 200 (got {width})")
        state.wrap_width = width
        return CommandResult(success=True, message=f"Text wrap width set to [bold]{width}[/bold]")

    if sub == "figsize":
        if len(args) < 3:
            return CommandResult(
                success=True,
                message=f"figsize = {state.plot_figsize[0]} {state.plot_figsize[1]}\n"
                "Usage: /settings figsize <width> <height>  (e.g. 8 6)",
            )
        try:
            w, h = int(args[1]), int(args[2])
        except ValueError:
            return CommandResult(success=False, message="Invalid figsize — must be two integers (e.g. 8 6)")
        if w < 2 or h < 2 or w > 30 or h > 30:
            return CommandResult(success=False, message=f"Figsize must be between 2 and 30 (got {w} {h})")
        state.plot_figsize = (w, h)
        return CommandResult(success=True, message=f"Plot figsize set to [bold]{w} x {h}[/bold]")

    if sub == "dpi":
        if len(args) < 2:
            return CommandResult(
                success=True,
                message=f"dpi = {state.plot_dpi}\nUsage: /settings dpi <value>  (50-600)",
            )
        try:
            dpi = int(args[1])
        except ValueError:
            return CommandResult(success=False, message=f"Invalid DPI: {args[1]} (must be integer)")
        if dpi < 50 or dpi > 600:
            return CommandResult(success=False, message=f"DPI must be between 50 and 600 (got {dpi})")
        state.plot_dpi = dpi
        return CommandResult(success=True, message=f"Plot DPI set to [bold]{dpi}[/bold]")

    if sub == "plotscale":
        if len(args) < 2:
            scale = _scale_label(state.plot_logx, state.plot_logy)
            return CommandResult(
                success=True,
                message=f"plotscale = {scale}\nUsage: /settings plotscale <loglog|linlin|loglin|linlog>",
            )
        choice = args[1].lower()
        if choice not in _VALID_SCALES:
            return CommandResult(
                success=False,
                message=f"Invalid scale: {choice}\nOptions: loglog, linlin, loglin, linlog",
            )
        state.plot_logx = choice.startswith("log")
        state.plot_logy = choice.endswith("log")
        return CommandResult(success=True, message=f"Default plot scale set to [bold]{choice}[/bold]")

    if sub == "errorbars":
        if len(args) < 2:
            return CommandResult(
                success=True,
                message=f"errorbars = {'on' if state.plot_errorbars else 'off'}\n"
                "Usage: /settings errorbars <on|off>",
            )
        choice = args[1].lower()
        if choice in ("on", "true", "yes", "1"):
            state.plot_errorbars = True
        elif choice in ("off", "false", "no", "0"):
            state.plot_errorbars = False
        else:
            return CommandResult(success=False, message=f"Invalid value: {choice} (use on/off)")
        return CommandResult(
            success=True,
            message=f"Default error bars set to [bold]{'on' if state.plot_errorbars else 'off'}[/bold]",
        )

    if sub == "linestyle":
        if len(args) < 2:
            return CommandResult(
                success=True,
                message=f"linestyle = {state.plot_linestyle}\n"
                "Usage: /settings linestyle <line|marker|line+marker>",
            )
        choice = args[1].lower()
        if choice not in _VALID_LINESTYLES:
            return CommandResult(
                success=False,
                message=f"Invalid linestyle: {choice}\nOptions: line, marker, line+marker",
            )
        state.plot_linestyle = choice
        return CommandResult(
            success=True,
            message=f"Default line style set to [bold]{choice}[/bold]",
        )

    return CommandResult(
        success=False,
        message=f"Unknown setting: {sub}\n"
        "Available: textwrap, figsize, dpi, plotscale, errorbars, linestyle",
    )
