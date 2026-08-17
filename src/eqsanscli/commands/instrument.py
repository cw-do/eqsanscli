"""/instrument — inspect and control instrument-file resolution.

The calibration set (dark current, sensitivity/flood, beam flux, and the AgBe
detector offset / scale components / sample offset) is resolved from the
machine-physics cycle folders based on each config's run number and detector
distance. See services/instrument_files.py for the selection policy.
"""

from __future__ import annotations

import os

from eqsanscli.commands.router import CommandResult
from eqsanscli.models.session_state import SessionState
from eqsanscli.services import instrument_files as ifiles
from eqsanscli.services.config_manager import _load_matching_preset
from eqsanscli.services.instrument_files import (
    MANAGED_PARAMS, PARAM_DARK, PARAM_FLUX, PARAM_SENSITIVITY,
)

_USAGE = (
    "Usage: /instrument <subcommand>\n"
    "  /instrument show               — what each config resolves to (default)\n"
    "  /instrument list [run]         — cycle inventory + what a run would pick\n"
    "  /instrument apply [--force]    — resolve now and write into the configs\n"
    "                                   --force also overwrites your own /set config edits\n"
    "  /instrument pin <cycle>        — always use one cycle (e.g. 2026A) regardless of run\n"
    "  /instrument unpin              — back to run-number based selection\n"
    "  /instrument off | on           — disable/enable automatic resolution at /matchruns\n"
    "  /instrument check              — verify every referenced file still exists\n"
)


def _fmt_value(param: str, value: object) -> str:
    """Paths shown as basenames — the folder is the same for a whole cycle."""
    if isinstance(value, str) and os.sep in value:
        return os.path.basename(value)
    if isinstance(value, list):
        return "[" + ", ".join(f"{v:g}" if isinstance(v, (int, float)) else str(v) for v in value) + "]"
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


async def handle_instrument(args: list[str], state: SessionState) -> CommandResult:
    """Dispatch /instrument <subcommand>."""
    if not args:
        return await _show(state)
    sub = args[0].lower()
    rest = args[1:]
    if sub in ("show", "status"):
        return await _show(state)
    if sub == "list":
        return await _list(rest, state)
    if sub == "apply":
        return await _apply(rest, state)
    if sub == "pin":
        return await _pin(rest, state)
    if sub in ("unpin", "auto"):
        state.instrument_cycle_pin = ""
        return CommandResult(
            success=True,
            message="Cycle pin cleared — instrument files follow each config's run number again.\n"
                    "  Run /instrument apply to re-resolve now.",
        )
    if sub in ("off", "disable"):
        state.auto_instrument_files = False
        return CommandResult(
            success=True,
            message="Automatic instrument-file resolution OFF. /matchruns and /autopilot will "
                    "leave these parameters alone; use /instrument apply to resolve manually.",
        )
    if sub in ("on", "enable"):
        state.auto_instrument_files = True
        return CommandResult(
            success=True,
            message="Automatic instrument-file resolution ON (applies at /matchruns and in autopilot).",
        )
    if sub == "check":
        return await _check(state)
    return CommandResult(success=False, message=f"Unknown /instrument subcommand: {sub}\n\n{_USAGE}")


async def _show(state: SessionState) -> CommandResult:
    targets = ifiles.config_targets(state)
    lines: list[str] = []

    mode = (
        f"pinned to cycle [bold]{state.instrument_cycle_pin}[/bold]"
        if state.instrument_cycle_pin else "by run number"
    )
    auto = "on" if state.auto_instrument_files else "[yellow]off[/yellow]"
    lines.append(f"[bold]Instrument files[/bold] — selection: {mode}, auto-apply: {auto}")
    lines.append(f"  source: {ifiles.mp_root()}")

    cycles = ifiles.scan_cycles()
    if not cycles:
        lines.append("  [red]No cycle folders found — nothing can be resolved.[/red]")
        return CommandResult(success=True, message="\n".join(lines))
    lines.append(f"  {len(cycles)} cycles available, newest {cycles[0].cycle_id} "
                 f"(from run {cycles[0].anchor_run})")

    if not targets:
        lines.append("\nWorking table is empty — run /matchruns first, or use "
                     "/instrument list <run> to preview a run.")
        return CommandResult(success=True, message="\n".join(lines))

    pin = state.instrument_cycle_pin or None
    for target in targets:
        resolution = ifiles.resolve_for_run(
            target.run, target.distance, cycles=cycles, pin_cycle=pin,
        )
        lines.append("")
        lines.append(
            f"[bold cyan]{target.config_id}[/bold cyan] — {target.n_rows} row(s), "
            f"run {target.run}{'' if target.max_run == target.run else f'-{target.max_run}'}, "
            f"{target.distance:g} m → cycle [bold]{resolution.cycle_id or '?'}[/bold]"
        )
        stored = state.configurations.get(target.config_id, {})
        provenance = state.instrument_provenance.get(target.config_id, {})
        preset = _load_matching_preset(target.config_id)
        for param in MANAGED_PARAMS:
            resolved = resolution.params.get(param)
            current = stored.get(param)
            if resolved is None:
                if current is not None:
                    lines.append(f"    {ifiles.PARAM_LABELS[param]:<17} "
                                 f"{_fmt_value(param, current)} [dim](kept — not resolved)[/dim]")
                continue
            # Same decision function apply uses, so the preview cannot lie.
            verdict = ifiles.classify_param(
                param, current, resolved.value, provenance, preset,
                absent=param not in stored,
            )
            if verdict == ifiles.UNCHANGED:
                mark, suffix = "[green]✓[/green]", ""
            elif verdict == ifiles.WRITE:
                mark = "[yellow]→[/yellow]"
                suffix = (
                    " [dim](not applied yet)[/dim]" if current is None
                    else f" [dim](replacing {_fmt_value(param, current)})[/dim]"
                )
            else:
                mark = "[yellow]![/yellow]"
                suffix = f" [dim](yours: {_fmt_value(param, current)} — kept)[/dim]"
            note = f" [dim]({resolved.note})[/dim]" if resolved.note else ""
            lines.append(f"    {mark} {ifiles.PARAM_LABELS[param]:<15} "
                         f"{_fmt_value(param, resolved.value)}{note}{suffix}")
        for miss in resolution.missing:
            lines.append(f"    [yellow]⚠[/yellow] {miss}")
        for note in resolution.notes:
            lines.append(f"    [dim]note: {note}[/dim]")

    lines.append("")
    lines.append("[dim]✓ in place · → apply will set this · ! your /set config value is kept "
                 "(use --force to overwrite)[/dim]")
    lines.append("[dim]Apply with /instrument apply[/dim]")
    return CommandResult(success=True, message="\n".join(lines))


async def _list(args: list[str], state: SessionState) -> CommandResult:
    cycles = ifiles.scan_cycles()
    if not cycles:
        return CommandResult(
            success=False,
            message=f"No cycle folders found under {ifiles.mp_root()}.",
        )

    run: int | None = None
    if args and args[0].isdigit():
        run = int(args[0])
    else:
        targets = ifiles.config_targets(state)
        if targets:
            run = min(t.run for t in targets)

    lines = [f"[bold]Machine-physics cycles[/bold] — {ifiles.mp_root()}"]
    lines.append(f"  {'cycle':<7} {'from run':>9}  {'dark':>5} {'floods':>7} {'flux':>5}  AgBe")
    selected = ifiles.select_cycle(run, cycles) if run else None
    for cycle in cycles:
        agbe = cycle.agbe
        agbe_txt = (
            f"detoffset={agbe.detoffset:.3f}" if agbe and agbe.detoffset is not None else "—"
        )
        dists = cycle.sensitivity_distances()
        marker = " [bold cyan]←[/bold cyan]" if selected and cycle is selected else ""
        lines.append(
            f"  {cycle.cycle_id:<7} {cycle.anchor_run:>9}  {len(cycle.darks):>5} "
            f"{'/'.join(f'{d:g}' for d in dists) or '—':>7} {len(cycle.flux):>5}  {agbe_txt}{marker}"
        )

    if run:
        lines.append("")
        lines.append(f"[bold]Resolution for run {run}[/bold] "
                     f"(→ cycle {selected.cycle_id if selected else '?'}):")
        for distance in (1.3, 2.5, 4.0, 8.0):
            resolution = ifiles.resolve_for_run(
                run, distance, cycles=cycles,
                pin_cycle=state.instrument_cycle_pin or None,
            )
            sens = resolution.params.get(PARAM_SENSITIVITY)
            note = f"  [dim]({sens.note})[/dim]" if sens and sens.note else ""
            lines.append(f"  {distance:>4g} m  "
                         f"{os.path.basename(str(sens.value)) if sens else '—'}{note}")
        first = ifiles.resolve_for_run(
            run, 4.0, cycles=cycles, pin_cycle=state.instrument_cycle_pin or None,
        )
        for param in (PARAM_DARK, PARAM_FLUX):
            resolved = first.params.get(param)
            lines.append(f"  {ifiles.PARAM_LABELS[param]:<9} "
                         f"{os.path.basename(str(resolved.value)) if resolved else '—'}")
        for miss in first.missing:
            lines.append(f"  [yellow]⚠[/yellow] {miss}")

    return CommandResult(success=True, message="\n".join(lines))


async def _apply(args: list[str], state: SessionState) -> CommandResult:
    force = any(a.lower() in ("--force", "-f") for a in args)
    if any(a.lower() == "--rescan" for a in args):
        ifiles.clear_cache()

    if not state.current_table.rows:
        return CommandResult(
            success=False,
            message="Working table is empty — run /matchruns first "
                    "(it resolves instrument files automatically).",
        )

    outcomes, warnings = ifiles.sync_state_configs(state, force=force)
    return CommandResult(success=True, message=format_outcomes(outcomes, warnings, verbose=True))


async def _pin(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(
            success=False,
            message="Usage: /instrument pin <cycle>   e.g. /instrument pin 2026A\n"
                    "  /instrument list shows the available cycles.",
        )
    wanted = args[0]
    cycles = ifiles.scan_cycles()
    match = next((c for c in cycles if c.cycle_id.lower() == wanted.lower()), None)
    if match is None:
        return CommandResult(
            success=False,
            message=f"Cycle '{wanted}' not found. Available: "
                    f"{', '.join(c.cycle_id for c in cycles) or '(none)'}",
        )
    state.instrument_cycle_pin = match.cycle_id
    return CommandResult(
        success=True,
        message=f"Pinned instrument files to cycle {match.cycle_id} — run numbers are ignored "
                f"until /instrument unpin.\n  Run /instrument apply to re-resolve now.",
    )


async def _check(state: SessionState) -> CommandResult:
    lines: list[str] = []
    problems = 0
    for config_id in sorted(c for c in state.configurations if c != "__all__"):
        found = ifiles.verify_paths(state.configurations[config_id])
        if found:
            problems += len(found)
            lines.append(f"[bold cyan]{config_id}[/bold cyan]")
            lines.extend(f"  [red]✗[/red] {p}" for p in found)
    if not state.configurations:
        return CommandResult(success=True, message="No configurations to check.")
    if problems:
        lines.append("")
        lines.append("Fix with /instrument apply (re-resolve) or /set config <id> <param> <path>.")
        return CommandResult(success=False, message="\n".join(lines))
    return CommandResult(
        success=True,
        message=f"All instrument files referenced by {len(state.configurations)} config(s) exist.",
    )


def format_outcomes(outcomes, warnings, *, verbose: bool = False) -> str:
    """Render apply results — shared with /matchruns and autopilot."""
    lines: list[str] = []
    if not outcomes:
        return "No configs to resolve instrument files for."

    for outcome in outcomes:
        resolution = outcome.resolution
        head = (
            f"  {outcome.config_id}: cycle {resolution.cycle_id or '?'}"
            if resolution.cycle_id else f"  {outcome.config_id}:"
        )
        if outcome.written:
            names = ", ".join(
                f"{ifiles.PARAM_LABELS[p]}={_fmt_value(p, v)}"
                for p, v in outcome.written.items()
            )
            lines.append(f"[green]✓[/green]{head} → {names}")
        elif outcome.unchanged:
            lines.append(f"[dim]·{head} already current[/dim]")
        else:
            lines.append(f"[dim]·{head} nothing resolved[/dim]")

        if outcome.kept_user:
            kept = ", ".join(
                f"{ifiles.PARAM_LABELS[p]}={_fmt_value(p, v)}"
                for p, v in outcome.kept_user.items()
            )
            lines.append(f"    [dim]kept your values: {kept}[/dim]")
        if verbose:
            for note in resolution.notes:
                lines.append(f"    [dim]note: {note}[/dim]")
        for miss in resolution.missing:
            lines.append(f"    [yellow]⚠[/yellow] {miss}")

    for warning in warnings:
        lines.append(f"  [yellow]⚠[/yellow] {warning}")
    return "\n".join(lines)
