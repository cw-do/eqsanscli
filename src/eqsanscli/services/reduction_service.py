from __future__ import annotations

import os
import threading
from pathlib import Path

from eqsanscli.integrations.drtsans_runner import ReductionResult, run_reduction
from eqsanscli.integrations.json_builder import build_reduction_json, save_reduction_json
from eqsanscli.models.working_table import WorkingTable, WorkingTableRow
from eqsanscli.services.config_manager import get_config


def reduce_row(
    row: WorkingTableRow,
    ipts: int,
    user_configs: dict[str, dict],
    output_dir: str = "./output/",
    filename_suffix: str = "",
    cancel_event: threading.Event | None = None,
    drtsans_version: str = "default",
) -> ReductionResult:
    # Cancelled before we started — return at once without building a JSON or
    # spawning drtsans. In a parallel batch, the executor keeps handing queued
    # rows to freed workers after the user cancels; this makes each such row a
    # no-op instead of a fresh ~1s drtsans launch that is immediately killed, so
    # a single cancel drains the whole queue at once.
    if cancel_event is not None and cancel_event.is_set():
        row.status = "cancelled"
        return ReductionResult(
            success=False, json_path="", output_file="",
            elapsed_seconds=0.0, stdout="", stderr="Cancelled before start.",
            return_code=-99, cancelled=True,
        )

    config_params = get_config(row.configuration, user_configs)

    output_name = row.output_stem
    if filename_suffix:
        output_name += f"_{filename_suffix}"

    json_data = build_reduction_json(
        ipts=ipts,
        scattering_run=row.scattering_run,
        sample_name=row.sample_name,
        transmission_run=row.transmission_run,
        background_scatt=row.background_scatt,
        background_trans=row.background_trans,
        empty_beam=row.empty_beam,
        thickness=row.thickness,
        config_params=config_params,
        output_dir=output_dir,
        output_filename=output_name,
    )

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    json_path = os.path.join(output_dir, f"{output_name}.json")
    save_reduction_json(json_data, json_path)

    result = run_reduction(json_path, cancel_event=cancel_event, drtsans_version=drtsans_version)

    standard_output = os.path.join(output_dir, f"{output_name}_Iq.dat")
    frame0_output = os.path.join(output_dir, f"{output_name}_frame_0_Iq.dat")

    if os.path.exists(frame0_output):
        result.output_file = frame0_output
    else:
        result.output_file = standard_output

    if result.cancelled:
        row.status = "cancelled"
    elif result.success:
        row.status = "done"
        row.output_file = result.output_file
    else:
        row.status = "error"

    return result


# --------------------------------------------------------------------------
# Preflight — what a row must have before drtsans can reduce it
# --------------------------------------------------------------------------
#
# Empty beam is mandatory: json_builder puts it in BOTH beamCenter.runNumber
# and emptyTransmission.runNumber, so without it the reduction has no beam
# centre. Transmission and background are advisory — drtsans accepts a
# transmission value instead of a run, and background-cell rows deliberately
# have no background (see matching_service.assign_background).


def blocking_problems(row: WorkingTableRow) -> list[str]:
    """Reasons this row cannot be reduced at all."""
    problems: list[str] = []
    if not str(row.scattering_run).strip():
        problems.append("no scattering run")
    if not str(row.empty_beam).strip():
        problems.append("no empty beam (needed for beam centre + empty transmission)")
    return problems


def advisory_problems(row: WorkingTableRow) -> list[str]:
    """Reasons this row will reduce but may not be what the user wants."""
    problems: list[str] = []
    if not str(row.transmission_run).strip():
        problems.append("no transmission")
    if not str(row.background_scatt).strip():
        problems.append("no background")
    try:
        if float(row.thickness) <= 0:
            problems.append(f"thickness={row.thickness}")
    except (TypeError, ValueError):
        problems.append(f"thickness={row.thickness!r} is not a number")
    return problems


def preflight(rows: list[WorkingTableRow]) -> tuple[
    list[tuple[WorkingTableRow, list[str]]], list[tuple[WorkingTableRow, list[str]]]
]:
    """Split `rows` into (blocked, advisory) with their reasons."""
    blocked = [(r, p) for r in rows if (p := blocking_problems(r))]
    advisory = [(r, p) for r in rows if not blocking_problems(r) and (p := advisory_problems(r))]
    return blocked, advisory


def format_preflight(
    blocked: list[tuple[WorkingTableRow, list[str]]],
    advisory: list[tuple[WorkingTableRow, list[str]]],
    *,
    n_selected: int,
    command: str = "/reduce",
) -> str:
    """Explain what is missing and exactly how to fix it."""
    lines: list[str] = []
    if blocked:
        lines.append(
            f"[red]✗ {len(blocked)} of {n_selected} selected row(s) cannot be reduced:[/red]"
        )
        for row, problems in blocked[:15]:
            lines.append(
                f"    Row {row.index}: {row.sample_name} (run {row.scattering_run or '—'}, "
                f"{row.configuration}) — {'; '.join(problems)}"
            )
        if len(blocked) > 15:
            lines.append(f"    ... and {len(blocked) - 15} more")

        missing_empty = [r for r, p in blocked if any("empty beam" in x for x in p)]
        if missing_empty:
            configs = sorted({r.configuration for r in missing_empty})
            lines.append("")
            lines.append(f"  Configurations without an empty beam: [bold]{', '.join(configs)}[/bold]")
            lines.append("  Fix one of these ways:")
            lines.append("    /show catalog                     find the empty-beam run (Class = EmpT)")
            lines.append("    /reclass <run> empty              if it exists but is misclassified,")
            lines.append("    /matchruns                        then re-match (assigns it per config)")
            lines.append(f"    /set --config <id> emp <run>      assign it to one configuration")
            lines.append("    /set <row> emp <run>              or just one row")
        lines.append("")
        lines.append(
            f"  [dim]{command} --skip-missing   reduce the {n_selected - len(blocked)} valid row(s) "
            f"and skip these[/dim]"
        )
        lines.append(
            f"  [dim]{command} --force          send them to drtsans anyway "
            f"(expect failures)[/dim]"
        )

    if advisory:
        if blocked:
            lines.append("")
        lines.append(f"[yellow]⚠ {len(advisory)} row(s) missing optional fields:[/yellow]")
        for row, problems in advisory[:10]:
            lines.append(
                f"    Row {row.index}: {row.sample_name} ({row.configuration}) — {', '.join(problems)}"
            )
        if len(advisory) > 10:
            lines.append(f"    ... and {len(advisory) - 10} more")
    return "\n".join(lines)


def parse_row_selection(selection: str, table: WorkingTable) -> list[int]:
    """Parse row selection: "1", "1-4", "1,3,5", "all" → list of 1-based indices.

    Accepts row index, run number, range, or "all".  For a single token that
    parses as an integer, tries row index first; if no row has that index,
    falls back to matching by scattering run number.
    """
    if selection.lower() == "all":
        return [r.index for r in table.rows]

    valid = {r.index for r in table.rows}
    run_to_index = {r.scattering_run: r.index for r in table.rows}

    indices: list[int] = []
    for part in selection.split(","):
        part = part.strip()
        try:
            if "-" in part:
                start, end = part.split("-", 1)
                indices.extend(range(int(start), int(end) + 1))
            else:
                val = int(part)
                if val in valid:
                    indices.append(val)
                elif part in run_to_index:
                    indices.append(run_to_index[part])
                else:
                    indices.append(val)  # keep for "not found" feedback
        except ValueError:
            # Non-numeric token — try as run number
            if part in run_to_index:
                indices.append(run_to_index[part])
            continue

    return [i for i in indices if i in valid]
