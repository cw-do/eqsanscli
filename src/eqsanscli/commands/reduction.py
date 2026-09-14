from __future__ import annotations

import os
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.models.sample_match import sample_matches
from eqsanscli.services.reduction_service import (
    format_preflight, output_dir_problem, parse_row_selection, preflight,
    reduce_row, timeslice_estimate,
)

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


def _format_time(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.0f}s"
    m, s = divmod(int(seconds), 60)
    return f"{m}m{s:02d}s"


def _summarize_error(out_file: str, err_file: str, fallback: str = "") -> str:
    for path in [out_file, err_file]:
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path) as f:
                lines = f.readlines()
            for line in reversed(lines):
                stripped = line.strip()
                if any(kw in stripped.lower() for kw in ["error", "exception", "traceback", "failed", "cannot"]):
                    return stripped[:150]
        except Exception:
            continue
    # No log/err file yet — e.g. the job failed before drtsans launched (a
    # non-writable output dir). Surface the result's own stderr in that case.
    if fallback.strip():
        return fallback.strip()[:150]
    return "unknown error (check .out and .err files)"


async def handle_reduce(args: list[str], state: SessionState) -> CommandResult:
    if not args or args[0].lower() == "help":
        return CommandResult(
            success=False,
            message="Usage: /reduce <row>\n"
            "       /reduce --sample <name>\n"
            "       /reduce --new\n"
            "  <row> = index, run number, range, or all\n"
            "  --new = reduce only rows whose status is not 'done' (new/error/modified)\n"
            "  Rows missing an empty beam are refused up front; add --skip-missing to\n"
            "  reduce the rest, or --force to send them to drtsans anyway.\n"
            "  Examples: /reduce 1  |  /reduce 172815  |  /reduce 1-4  |  /reduce all\n"
            "            /reduce --sample porsil  |  /reduce --sample *3b*  |  /reduce --new",
        )

    # Preflight modifiers, stripped before selection parsing.
    force = any(a.lower() in ("--force", "-f") for a in args)
    skip_missing = any(a.lower() in ("--skip-missing", "--skip") for a in args)
    args = [a for a in args if a.lower() not in ("--force", "-f", "--skip-missing", "--skip")]
    if not args:
        return CommandResult(
            success=False,
            message="Usage: /reduce <row> [--skip-missing | --force]\n"
            "  Give rows to reduce, e.g. /reduce all --skip-missing",
        )

    table = state.current_table
    if not table.rows:
        return CommandResult(success=False, message="Working table is empty. Use /matchruns first.")

    if args[0] == "--sample":
        if len(args) < 2:
            return CommandResult(success=False, message="Usage: /reduce --sample <name>")
        pattern = args[1]
        indices = [r.index for r in table.rows if sample_matches(pattern, r.sample_name)]
        if not indices:
            return CommandResult(success=False, message=f"No rows with sample name matching: {pattern}")
    elif args[0] == "--new":
        indices = [r.index for r in table.rows if r.status != "done"]
        if not indices:
            return CommandResult(
                success=True,
                message="No rows to reduce — all rows are already 'done'.",
            )
    else:
        selection = args[0]
        indices = parse_row_selection(selection, table)
        if not indices:
            return CommandResult(success=False, message=f"No valid rows for selection: {selection}")

    # Preflight: an empty beam is mandatory (beam centre). Refuse rather than let
    # drtsans fail per row with an opaque error.
    selected = [r for r in table.rows if r.index in set(indices)]
    blocked, advisory = preflight(selected)
    report = format_preflight(blocked, advisory, n_selected=len(selected))

    if blocked and not (force or skip_missing):
        return CommandResult(success=False, message=report)

    if blocked and skip_missing:
        blocked_indices = {r.index for r, _ in blocked}
        indices = [i for i in indices if i not in blocked_indices]
        if not indices:
            return CommandResult(
                success=False,
                message=report + "\n\n[red]Nothing left to reduce — every selected row is "
                "missing something required.[/red]",
            )

    prefix = ""
    if blocked and force:
        prefix = (
            f"[yellow]⚠ --force: reducing {len(blocked)} row(s) that are missing required "
            f"fields — expect drtsans failures.[/yellow]\n"
        )
    elif blocked and skip_missing:
        prefix = (
            f"[yellow]⚠ Skipping {len(blocked)} row(s) missing required fields; "
            f"reducing {len(indices)}.[/yellow]\n"
        )
    elif advisory:
        prefix = report + "\n"

    # Every output directory in play must be writable, or those rows would fail
    # the same way (or, before the guard, crash the app). Rows can each target a
    # different dir now (per-row `/set <rows> outputdir`), so check each distinct
    # effective dir once, up front, with a fix.
    checked: set[str] = set()
    for idx in indices:
        row = table.get_row(idx)
        if row is None:
            continue
        eff = (row.output_override or "").strip() or state.output_directory
        if eff in checked:
            continue
        checked.add(eff)
        problem = output_dir_problem(eff)
        if problem:
            where = f" for row(s) → {os.path.abspath(eff)}" if row.output_override else ""
            return CommandResult(
                success=False,
                message=f"[red]Cannot reduce — output directory {problem}{where}.[/red]\n"
                f"  Set a writable one with [cyan]/set outputdir <path>[/cyan] "
                f"(session-wide) or [cyan]/set <rows> outputdir <path>[/cyan] (per row).",
            )

    # Time-slicing multiplies the work: one full reduction per slice. Tell the
    # user the slice count up front (per config) so a too-fine interval is caught
    # before an hours-long run, and so the long runtime is expected.
    prefix += _timeslice_notice(indices, table, state)

    return CommandResult(
        success=True,
        message=prefix,
        data={"type": "start_reduction", "indices": indices},
    )


def _timeslice_notice(indices, table, state) -> str:
    """A per-config line for any selected row whose config uses time-slicing."""
    from eqsanscli.services.config_manager import get_config
    seen: set[str] = set()
    lines: list[str] = []
    for idx in indices:
        row = table.get_row(idx)
        if row is None or row.configuration in seen:
            continue
        cfg = get_config(row.configuration, state.configurations)
        est = timeslice_estimate(cfg, state.run_duration(row.scattering_run))
        if est is None:
            continue
        seen.add(row.configuration)
        n, interval, dur = est["slices"], est["interval_s"], est["duration_s"]
        colour = "yellow" if n > 200 else "cyan"
        caution = ("  [bold]— that is a lot of slices; check the interval matches "
                   "the timescale you care about[/bold]" if n > 200 else "")
        lines.append(
            f"[{colour}]⏱ Time-slicing {row.configuration}: ~{n} slices/run "
            f"({dur}s ÷ {interval:g}s){caution}[/{colour}]\n"
            f"  [dim]drtsans writes a full I(Q)/I(Qx,Qy)/NeXus set per slice; "
            f"this run will take a while and produce {n}× the files.[/dim]"
        )
    return ("\n".join(lines) + "\n") if lines else ""
