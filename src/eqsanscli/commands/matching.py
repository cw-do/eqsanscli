"""Matching command handlers — /matchruns, /set, /assign bkg."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.commands.catalog import build_working_table_display
from eqsanscli.models.config_id import make_config_id
from eqsanscli.models.sample_match import sample_matches
from eqsanscli.services.matching_service import (
    assign_background, match_runs, merge_new_runs, _classify_catalog,
)
from eqsanscli.services.reduction_service import parse_row_selection

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


async def handle_matchruns(args: list[str], state: SessionState) -> CommandResult:
    """Handle /matchruns — auto-match trans/bkg/empty runs from catalog.

    Flags:
      --update  Add only new scattering runs to the existing table; preserve
                already-reduced rows and their status. New rows inherit bkg/empty
                from existing rows in the same config. Use after /refresh catalog.
    """
    catalog = state.catalog
    if catalog is None or catalog.empty:
        return CommandResult(
            success=False,
            message="No catalog loaded. Use /show <ipts> first.",
        )

    update_mode = any(a.lower() in ("--update", "-u") for a in args)

    if update_mode:
        existing = state.current_table
        if not existing.rows:
            return CommandResult(
                success=False,
                message="/matchruns --update needs an existing working table. "
                        "Run /matchruns (without --update) first.",
            )
        table, match_warnings, n_new, new_config_ids = merge_new_runs(
            existing, catalog, ipts=state.ipts
        )
    else:
        table, match_warnings = match_runs(catalog, ipts=state.ipts)
        n_new = None
        new_config_ids = []

    if not table.rows:
        return CommandResult(
            success=True,
            message="No scattering runs found to match. Check catalog titles.",
        )

    state.tables[state.active_table] = table
    table.name = state.active_table

    for cfg in table.configurations:
        if cfg not in state.configurations:
            state.configurations[cfg] = {}
        state.configurations[cfg].setdefault("outputdir", os.path.abspath(state.output_directory))

    configs = table.configurations
    matched_trans = sum(1 for r in table.rows if r.transmission_run)
    matched_bkg = sum(1 for r in table.rows if r.background_scatt)
    matched_empty = sum(1 for r in table.rows if r.empty_beam)

    if update_mode:
        done_count = sum(1 for r in table.rows if r.status == "done")
        summary = (
            f"Updated working table: +{n_new} new row(s), {done_count} preserved as 'done'.\n"
            f"  Total: {len(table.rows)} rows across {len(configs)} configurations.\n"
            f"  Configurations: {', '.join(configs)}"
        )
        if new_config_ids:
            summary += f"\n  ⚠ New configuration(s): {', '.join(new_config_ids)} — run /apply preset auto to assign presets."
        if n_new == 0:
            summary += "\n  No new scattering runs found — table is unchanged."
        summary += (
            f"\n  Transmission matched: {matched_trans}/{len(table.rows)}\n"
            f"  Background matched: {matched_bkg}/{len(table.rows)}\n"
            f"  Empty beam matched: {matched_empty}/{len(table.rows)}"
        )
    else:
        summary = (
            f"Matched {len(table.rows)} scattering runs across {len(configs)} configurations.\n"
            f"  Configurations: {', '.join(configs)}\n"
            f"  Transmission matched: {matched_trans}/{len(table.rows)}\n"
            f"  Background matched: {matched_bkg}/{len(table.rows)}\n"
            f"  Empty beam matched: {matched_empty}/{len(table.rows)}"
        )

    missing_trans = [r for r in table.rows if not r.transmission_run]
    missing_bkg = [r for r in table.rows if not r.background_scatt]
    missing_empty = [r for r in table.rows if not r.empty_beam]

    if missing_trans or missing_bkg or missing_empty:
        classified = _classify_catalog(catalog)

        used_runs: set[str] = set()
        for r in table.rows:
            used_runs.add(r.scattering_run)
            if r.transmission_run:
                used_runs.add(r.transmission_run)
            if r.background_scatt:
                used_runs.add(r.background_scatt)
            if r.background_trans:
                used_runs.add(r.background_trans)
            if r.empty_beam:
                used_runs.add(r.empty_beam)

        lines: list[str] = []

        if missing_trans:
            lines.append(f"\n⚠ {len(missing_trans)} row(s) missing transmission:")
            for r in missing_trans:
                lines.append(f"  Row {r.index}: {r.sample_name} ({r.configuration})")
            avail_trans = [
                cr for cr in classified
                if cr.run_type == "transmission" and str(cr.run_number) not in used_runs
            ]
            if avail_trans:
                lines.append("  Available transmission runs (unused):")
                for cr in avail_trans:
                    cfg = make_config_id(cr.config_key[0], cr.config_key[1], cr.config_key[2])
                    lines.append(f"    {cr.run_number}  {cr.title}  [{cfg}]")

        if missing_bkg:
            lines.append(f"\n⚠ {len(missing_bkg)} row(s) missing background:")
            for r in missing_bkg:
                lines.append(f"  Row {r.index}: {r.sample_name} ({r.configuration})")

        if missing_empty:
            lines.append(f"\n⚠ {len(missing_empty)} row(s) missing empty beam:")
            for r in missing_empty:
                lines.append(f"  Row {r.index}: {r.sample_name} ({r.configuration})")

        summary += "\n" + "\n".join(lines)
        summary += "\n\nTip: Use /set --sample <name> <field> <value> to fix unmatched rows in bulk."

    if match_warnings:
        summary += "\n\n" + "\n".join(f"⚠ {w}" for w in match_warnings)

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

    if first == "drtsans":
        from eqsanscli.integrations.drtsans_runner import DRTSANS_VERSIONS
        valid = ", ".join(DRTSANS_VERSIONS.keys())
        if len(args) < 2:
            return CommandResult(success=True, message=f"drtsans version = {state.drtsans_version}\n  Available: {valid}")
        version = args[1].lower()
        if version not in DRTSANS_VERSIONS:
            return CommandResult(success=False, message=f"Unknown version: {version}. Available: {valid}")
        state.drtsans_version = version
        cmd = " ".join(DRTSANS_VERSIONS[version])
        return CommandResult(success=True, message=f"drtsans version set to: {version} ({cmd})")

    # Bulk set: /set --sample <name> <field> <value>
    # Matches all rows whose sample_name contains <name> (case-insensitive).
    if first == "--sample":
        if len(args) < 4:
            return CommandResult(
                success=False,
                message="Usage: /set --sample <name> <field> <value>\n"
                "  Example: /set --sample 3b trans 172804\n"
                "  Matches all rows whose sample name contains <name> (case-insensitive).",
            )
        sample_pattern = args[1]
        field_name = args[2].lower()
        value_str = " ".join(args[3:])

        if field_name not in SETTABLE_FIELDS:
            return CommandResult(
                success=False,
                message=f"Unknown field: {field_name}. Valid fields: {', '.join(SETTABLE_FIELDS.keys())}",
            )

        attr_name = SETTABLE_FIELDS[field_name]
        table = state.current_table

        matching_rows = [
            r for r in table.rows if sample_matches(sample_pattern, r.sample_name)
        ]
        if not matching_rows:
            return CommandResult(
                success=False,
                message=f"No rows with sample name containing '{args[1]}' in table '{table.name}'.",
            )

        if value_str.lower() in ("none", "null", '""', "''", ""):
            if attr_name == "thickness":
                return CommandResult(success=False, message="Cannot clear thickness — set a numeric value.")
            for row in matching_rows:
                row.set_field(attr_name, "")
            return CommandResult(
                success=True,
                message=f"Cleared {field_name} for {len(matching_rows)} row(s) matching '{args[1]}'.",
            )

        if attr_name == "thickness":
            try:
                parsed_value: str | float = float(value_str)
            except ValueError:
                return CommandResult(success=False, message=f"Invalid thickness value: {value_str}")
        else:
            parsed_value = value_str

        for row in matching_rows:
            row.set_field(attr_name, parsed_value)

        sample_list = ", ".join(sorted(set(r.sample_name for r in matching_rows)))
        return CommandResult(
            success=True,
            message=f"Set {field_name}={value_str} for {len(matching_rows)} row(s) matching '{args[1]}'.\n"
            f"  Samples: {sample_list}",
        )

    if len(args) < 3:
        return CommandResult(
            success=False,
            message="Usage: /set <row> <field> <value> | /set outputdir <path> | /set ipts <number>\n"
            "  <row> = index, run number, range, or all\n"
            "  Use 'none' to clear a value.\n"
            f"  Row fields: {', '.join(SETTABLE_FIELDS.keys())}",
        )

    run_id = args[0]
    field_name = args[1].lower()
    value_str = " ".join(args[2:])

    if field_name not in SETTABLE_FIELDS:
        return CommandResult(
            success=False,
            message=f"Unknown field: {field_name}. Valid fields: {', '.join(SETTABLE_FIELDS.keys())}",
        )

    attr_name = SETTABLE_FIELDS[field_name]
    table = state.current_table

    indices = parse_row_selection(run_id, table)
    target_rows = [r for r in table.rows if r.index in indices]

    if not target_rows:
        return CommandResult(
            success=False,
            message=f"'{run_id}' not found as row index, range, or scattering run in table '{table.name}'.",
        )

    if value_str.lower() in ("none", "null", '""', "''", ""):
        if attr_name == "thickness":
            return CommandResult(success=False, message="Cannot clear thickness — set a numeric value.")
        for r in target_rows:
            r.set_field(attr_name, "")
        label = f"{len(target_rows)} row(s)" if len(target_rows) > 1 else f"run {run_id} ({target_rows[0].sample_name})"
        return CommandResult(success=True, message=f"Cleared {field_name} for {label}.")

    if attr_name == "thickness":
        try:
            parsed_value: str | float = float(value_str)
        except ValueError:
            return CommandResult(success=False, message=f"Invalid thickness value: {value_str}")
    else:
        parsed_value = value_str

    for r in target_rows:
        r.set_field(attr_name, parsed_value)

    label = f"{len(target_rows)} row(s)" if len(target_rows) > 1 else f"run {run_id} ({target_rows[0].sample_name})"
    return CommandResult(
        success=True,
        message=f"Set {field_name}={value_str} for {label}.",
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
            message="Usage: /remove <row> [--keep <sample>] | /remove --sample <name>\n"
            "  <row> = index, run number, range, or all\n"
            "  /remove 3  |  /remove 172815  |  /remove 1-5  |  /remove all --keep porsil  |  /remove --sample banjo",
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
            keep_sample = args[i]
        elif a == "--sample" and i + 1 < len(args):
            i += 1
            remove_sample = args[i]
        elif row_spec is None:
            row_spec = args[i]
        i += 1

    if remove_sample:
        indices = [r.index for r in table.rows if sample_matches(remove_sample, r.sample_name)]
        if not indices:
            return CommandResult(success=False, message=f"No rows with sample name matching: {remove_sample}")
    elif row_spec and row_spec.lower() == "all" and keep_sample:
        indices = [r.index for r in table.rows if not sample_matches(keep_sample, r.sample_name)]
        if not indices:
            return CommandResult(success=True, message=f"Nothing to remove — all rows match '{keep_sample}'.")
    elif row_spec:
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
