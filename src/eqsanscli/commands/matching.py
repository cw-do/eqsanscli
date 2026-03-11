"""Matching command handlers — /matchruns, /set, /assign bkg."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.commands.catalog import build_working_table_display
from eqsanscli.services.matching_service import assign_background, match_runs

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


async def handle_matchruns(args: list[str], state: SessionState) -> CommandResult:
    """Handle /matchruns — auto-match trans/bkg/empty runs from catalog."""
    catalog = state.catalog
    if catalog is None or catalog.empty:
        return CommandResult(
            success=False,
            message="No catalog loaded. Use /show <ipts> first.",
        )

    table = match_runs(catalog, ipts=state.ipts)

    if not table.rows:
        return CommandResult(
            success=True,
            message="No scattering runs found to match. Check catalog titles.",
        )

    # Store as the active table
    state.tables[state.active_table] = table
    table.name = state.active_table

    # Build summary
    configs = table.configurations
    matched_trans = sum(1 for r in table.rows if r.transmission_run)
    matched_bkg = sum(1 for r in table.rows if r.background_scatt)
    matched_empty = sum(1 for r in table.rows if r.empty_beam)

    summary = (
        f"Matched {len(table.rows)} scattering runs across {len(configs)} configurations.\n"
        f"  Configurations: {', '.join(configs)}\n"
        f"  Transmission matched: {matched_trans}/{len(table.rows)}\n"
        f"  Background matched: {matched_bkg}/{len(table.rows)}\n"
        f"  Empty beam matched: {matched_empty}/{len(table.rows)}"
    )

    rows = build_working_table_display(state)

    return CommandResult(
        success=True,
        message=summary,
        data={"type": "working_table", "rows": rows},
    )


SETTABLE_FIELDS = {
    "trans": "transmission_run",
    "transmission": "transmission_run",
    "bkg": "background_scatt",
    "bkgscatt": "background_scatt",
    "bkgtrans": "background_trans",
    "emp": "empty_beam",
    "empty": "empty_beam",
    "thickness": "thickness",
}


async def handle_set(args: list[str], state: SessionState) -> CommandResult:
    """Handle /set <run> <field> <value> — set a run association on a working table row.

    Run number values are strings (supports comma-separated multi-run like "111, 112").
    Use "none", "null", or "" to clear a value.

    Examples:
        /set 167942 trans 167931
        /set 167942 bkg 167940
        /set 167942 emp 167929
        /set 167942 bkg none            ← clears background
        /set 167942 trans "111, 112"    ← multi-run for combined statistics
        /set 167942 thickness 0.1
    """
    if not args:
        return CommandResult(
            success=False,
            message="Usage: /set <run> <field> <value> | /set outputdir <path> | /set ipts <number>",
        )

    first = args[0].lower()

    if first == "outputdir":
        if len(args) < 2:
            return CommandResult(success=True, message=f"outputdir = {os.path.abspath(state.output_directory)}")
        new_dir = os.path.abspath(" ".join(args[1:]))
        state.output_directory = new_dir
        configs = state.current_table.configurations
        for cfg in configs:
            if cfg not in state.configurations:
                state.configurations[cfg] = {}
            state.configurations[cfg]["outputdir"] = new_dir
        n = len(configs)
        return CommandResult(
            success=True,
            message=f"Output directory set to: {new_dir}\n"
            f"  Applied to {n} config(s): {', '.join(configs) if configs else 'none yet'}",
        )

    if first == "ipts":
        if len(args) < 2:
            return CommandResult(success=True, message=f"ipts = {state.ipts}")
        try:
            state.ipts = int(args[1])
        except ValueError:
            return CommandResult(success=False, message=f"Invalid IPTS number: {args[1]}")
        return CommandResult(success=True, message=f"IPTS set to: {state.ipts}")

    if len(args) < 3:
        return CommandResult(
            success=False,
            message="Usage: /set <run> <field> <value> | /set outputdir <path> | /set ipts <number>\n"
            "  Use 'none' to clear a value.\n"
            f"  Row fields: {', '.join(SETTABLE_FIELDS.keys())}",
        )

    run_id = args[0]
    field_name = args[1].lower()
    # Join remaining args to support quoted multi-run strings
    value_str = " ".join(args[2:])

    if field_name not in SETTABLE_FIELDS:
        return CommandResult(
            success=False,
            message=f"Unknown field: {field_name}. Valid fields: {', '.join(SETTABLE_FIELDS.keys())}",
        )

    attr_name = SETTABLE_FIELDS[field_name]

    # Find the row by scattering run number (string match)
    table = state.current_table
    target_row = None
    for row in table.rows:
        if row.scattering_run == run_id:
            target_row = row
            break

    if target_row is None:
        return CommandResult(
            success=False,
            message=f"Run {run_id} not found in working table '{table.name}'.",
        )

    # Parse value — support "none"/"null"/"" to clear
    if value_str.lower() in ("none", "null", '""', "''", ""):
        if attr_name == "thickness":
            return CommandResult(success=False, message="Cannot clear thickness — set a numeric value.")
        setattr(target_row, attr_name, "")
        return CommandResult(
            success=True,
            message=f"Cleared {field_name} for run {run_id} ({target_row.sample_name}).",
        )

    if attr_name == "thickness":
        try:
            parsed_value: str | float = float(value_str)
        except ValueError:
            return CommandResult(success=False, message=f"Invalid thickness value: {value_str}")
    else:
        # Run number fields are strings — accept as-is (supports "111, 112")
        parsed_value = value_str

    setattr(target_row, attr_name, parsed_value)

    return CommandResult(
        success=True,
        message=f"Set {field_name}={value_str} for run {run_id} ({target_row.sample_name}).",
    )


async def handle_remove(args: list[str], state: SessionState) -> CommandResult:
    """/remove <rows|all> [--keep <sample>] — remove rows by index or filter by sample name.

    /remove 3                   — remove row 3
    /remove 1,4,7               — remove rows 1, 4, 7
    /remove 5-10                — remove rows 5 through 10
    /remove all --keep porsil   — remove all rows EXCEPT those with sample name "porsil"
    /remove --sample banjo      — remove all rows with sample name "banjo"
    """
    if not args:
        return CommandResult(
            success=False,
            message="Usage: /remove <rows|all> [--keep <sample>] | /remove --sample <name>\n"
            "  /remove 3  |  /remove 1-5  |  /remove all --keep porsil  |  /remove --sample banjo",
        )

    table = state.current_table
    if not table.rows:
        return CommandResult(success=False, message="Working table is empty.")

    keep_sample = None
    remove_sample = None
    row_spec = None
    i = 0
    while i < len(args):
        a = args[i].lower()
        if a in ("--keep", "--except", "--but") and i + 1 < len(args):
            i += 1
            keep_sample = args[i].lower()
        elif a == "--sample" and i + 1 < len(args):
            i += 1
            remove_sample = args[i].lower()
        elif row_spec is None:
            row_spec = args[i]
        i += 1

    if remove_sample:
        indices = [r.index for r in table.rows if r.sample_name.lower() == remove_sample]
        if not indices:
            return CommandResult(success=False, message=f"No rows with sample name: {remove_sample}")
    elif row_spec and row_spec.lower() == "all" and keep_sample:
        indices = [r.index for r in table.rows if r.sample_name.lower() != keep_sample]
        if not indices:
            return CommandResult(success=True, message=f"Nothing to remove — all rows match '{keep_sample}'.")
    elif row_spec:
        from eqsanscli.services.reduction_service import parse_row_selection
        indices = parse_row_selection(row_spec, table)
        if not indices:
            return CommandResult(success=False, message=f"No valid rows for: {row_spec}")
    else:
        return CommandResult(success=False, message="No rows specified.")

    removed = []
    for idx in sorted(indices, reverse=True):
        row = table.remove_row(idx)
        if row:
            removed.append(f"{row.sample_name} ({row.configuration})")

    return CommandResult(
        success=True,
        message=f"Removed {len(removed)} row(s).\n"
        f"  Table '{table.name}' now has {len(table.rows)} rows.",
    )


async def handle_assign(args: list[str], state: SessionState) -> CommandResult:
    """Handle /assign bkg <sample_name> — reassign background for all samples.

    Examples:
        /assign bkg s0      → use S-s0 / T-s0 as background for all other samples
        /assign bkg banjo   → use S-banjo / T-banjo as background (default)
    """
    if len(args) < 2:
        return CommandResult(
            success=False,
            message="Usage: /assign bkg <sample_name>\n"
            "  Example: /assign bkg s0",
        )

    field = args[0].lower()
    if field != "bkg":
        return CommandResult(
            success=False,
            message=f"Unknown /assign target: {field}. Currently only 'bkg' is supported.",
        )

    bkg_sample_name = args[1]
    catalog = state.catalog
    if catalog is None or catalog.empty:
        return CommandResult(
            success=False,
            message="No catalog loaded. Use /show <ipts> first.",
        )

    table = state.current_table
    if not table.rows:
        return CommandResult(
            success=False,
            message="Working table is empty. Use /matchruns first.",
        )

    count, message = assign_background(table, catalog, bkg_sample_name)

    if count == 0:
        return CommandResult(success=False, message=message)

    rows = build_working_table_display(state)
    return CommandResult(
        success=True,
        message=message,
        data={"type": "working_table", "rows": rows},
    )
