"""Matching command handlers — /matchruns, /set, /assign bkg."""

from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.commands.catalog import build_working_table_display
from eqsanscli.models.config_id import config_ids_match, make_config_id
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

    from eqsanscli.services.config_manager import ALL_CONFIGS_KEY, _load_matching_preset
    all_defaults = state.configurations.get(ALL_CONFIGS_KEY, {})
    preset_applied: list[str] = []
    preset_missing: list[str] = []
    for cfg in table.configurations:
        if cfg not in state.configurations:
            state.configurations[cfg] = {}
        cfg_dict = state.configurations[cfg]
        cfg_dict.setdefault("outputdir", os.path.abspath(state.output_directory))
        # Propagate any "/set config all <param> <val>" defaults onto this config
        for k, v in all_defaults.items():
            cfg_dict.setdefault(k, v)
        # Auto-apply matching JSON preset from preset_configs/ (setdefault — never
        # overwrites a value the user already set, and None values were dropped).
        preset_params = _load_matching_preset(cfg)
        if preset_params:
            n_filled = 0
            for k, v in preset_params.items():
                if k not in cfg_dict:
                    cfg_dict[k] = v
                    n_filled += 1
            if n_filled:
                preset_applied.append(f"{cfg} ({n_filled})")
        else:
            preset_missing.append(cfg)

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
            summary += f"\n  New configuration(s): {', '.join(new_config_ids)}"
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

    if preset_applied:
        summary += f"\n  Presets auto-applied: {', '.join(preset_applied)}"
    if preset_missing:
        summary += (
            f"\n  ⚠ No matching preset for: {', '.join(preset_missing)} "
            f"— using drtsans defaults. Add a JSON preset to preset_configs/ or "
            f"use /set config to override."
        )

    # Instrument calibration files (dark/flood/flux + AgBe offsets) come from the
    # machine-physics cycle folders, chosen by run number — they are cycle-specific,
    # so the JSON presets' hardcoded paths go stale every cycle. Runs after the
    # preset apply, so preset values are the thing being refreshed; explicit
    # /set config edits are preserved.
    if state.auto_instrument_files:
        from eqsanscli.commands.instrument import format_mask_note, format_outcomes
        from eqsanscli.services.instrument_files import sync_state_configs

        outcomes, inst_warnings = sync_state_configs(state)
        if outcomes:
            summary += "\n  Instrument files (machine physics):\n"
            summary += format_outcomes(outcomes, inst_warnings)
            mask_note = format_mask_note(outcomes)
            if mask_note:
                summary += "\n" + mask_note
            summary += "\n  [dim]/instrument show for detail; /instrument off to manage by hand[/dim]"
    else:
        summary += "\n  [dim]Instrument-file resolution is off (/instrument on to enable)[/dim]"

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
    "sample": "sample_name",
    "name": "sample_name",
    "sample_name": "sample_name",
    # 'cfg' is canonical; 'config'/'configuration' kept as aliases.
    # Canonical name avoids collision with the `/set config <id> <param> <val>`
    # sub-command form (which routes via the compound "set config" handler).
    "cfg": "configuration_override",
    "config": "configuration_override",
    "configuration": "configuration_override",
}


# Run-assignment fields — the only ones that may be combined in one /set, because
# they all take the same value semantics (a run-number string, or a clear).
_RUN_FIELDS = frozenset({
    "transmission_run", "background_scatt", "background_trans", "empty_beam",
})

# attr name → canonical short label, for echoing back what was set.
_FIELD_SHORT = {
    "transmission_run": "trans",
    "background_scatt": "bkg",
    "background_trans": "bkgtrans",
    "empty_beam": "emp",
    "thickness": "thickness",
    "sample_name": "sample",
    "configuration_override": "cfg",
}


def _resolve_fields(field_token: str) -> tuple[list[str], str]:
    """Resolve a field token to a list of attr names.

    A token may name several fields with ``,`` or ``+`` (e.g. ``trans,emp``) so a
    single run can be assigned to both at once. Returns (attr_names, bad_name);
    bad_name is the first unrecognized field, or "" on success.
    """
    parts = [p for p in re.split(r"[,+]", field_token.lower()) if p]
    attrs: list[str] = []
    for p in parts:
        if p not in SETTABLE_FIELDS:
            return [], p
        attr = SETTABLE_FIELDS[p]
        if attr not in attrs:
            attrs.append(attr)
    return attrs, ""


def _apply_field_set(
    target_rows: list, attr_names: list[str], value_str: str, state,
) -> tuple[bool, str, str]:
    """Set one or more fields on the given rows.

    Returns (ok, display_value, error). Combining fields is only allowed for the
    run-assignment fields (they share value semantics); mixing in thickness /
    sample / cfg is rejected with guidance rather than guessed.
    """
    clearing = value_str.strip().lower() in ("none", "null", '""', "''", "")

    if len(attr_names) > 1:
        non_run = [_FIELD_SHORT[a] for a in attr_names if a not in _RUN_FIELDS]
        if non_run:
            return False, "", (
                f"Cannot combine {', '.join(non_run)} with other fields — only run "
                f"assignments (trans, bkg, bkgtrans, emp) can be set together. "
                f"Set {', '.join(non_run)} on its own."
            )

    if clearing:
        for a in attr_names:
            if a == "thickness":
                return False, "", "Cannot clear thickness — set a numeric value."
            if a == "sample_name":
                return False, "", "Cannot clear sample_name — provide a non-empty name."
        for r in target_rows:
            for a in attr_names:
                r.set_field(a, "")
        return True, "(cleared)", ""

    # Single special-field forms keep their dedicated parsing/validation.
    if attr_names == ["thickness"]:
        try:
            pv = float(value_str)
        except ValueError:
            return False, "", f"Invalid thickness value: {value_str}"
        for r in target_rows:
            r.set_field("thickness", pv)
        return True, str(pv), ""
    if attr_names == ["configuration_override"]:
        ok, resolved, err = _validate_config_target(value_str, state, target_rows)
        if not ok:
            return False, "", err
        for r in target_rows:
            r.set_field("configuration_override", resolved)
        return True, resolved, ""

    # Run fields (and sample_name) — plain string value applied to every attr.
    for r in target_rows:
        for a in attr_names:
            r.set_field(a, value_str)
    return True, value_str, ""


def _field_label(attr_names: list[str]) -> str:
    return "+".join(_FIELD_SHORT.get(a, a) for a in attr_names)


def _validate_config_target(value: str, state, rows: list | None = None) -> tuple[bool, str, str]:
    """Validate that `value` names a config the given rows may reference.

    Returns (ok, resolved_value, error_message). On success, resolved_value
    is the stored key from state.configurations (preserving the user's
    casing/format). Accepts "none"/"null"/"" as a clear → returns ("").
    Also accepts any physical config currently in the table (no override
    needed — but storing the explicit name is harmless and makes the
    intent visible in /show table).

    When `rows` is given, the target's physics must match every row's own
    physical configuration: pointing a 4m10a row at 8m parameters (or at a
    clone of them) would reduce it with the wrong distance/wavelength setup,
    which is a mistake rather than a valid override.
    """
    from eqsanscli.models.config_id import base_config_id, normalize_config_id
    from eqsanscli.services.config_manager import ALL_CONFIGS_KEY

    v = value.strip()
    if v.lower() in ("none", "null", ""):
        return True, "", ""

    norm = normalize_config_id(v)
    if not norm:
        return False, "", f"Invalid config name: '{value}'"

    resolved: str | None = None

    # 1) Stored override in state.configurations
    for k in state.configurations:
        if k == ALL_CONFIGS_KEY:
            continue
        if normalize_config_id(k) == norm:
            resolved = k
            break

    # 2) A physical config already present in the table (no clone needed)
    table = state.current_table
    if resolved is None:
        for cfg in table.configurations:
            if normalize_config_id(cfg) == norm:
                resolved = cfg
                break

    if resolved is None:
        from eqsanscli.commands.config import _dedup_config_names
        available = _dedup_config_names(state, table)
        return (
            False,
            "",
            f"Unknown config '{value}'. Use /config clone <src> {value} first, or pick from: "
            f"{', '.join(available) or '(none)'}",
        )

    # 3) Physics must match the rows being reassigned
    target_base = base_config_id(resolved)
    if rows and target_base:
        mismatched = [
            r for r in rows
            if normalize_config_id(r.physical_configuration) != normalize_config_id(target_base)
        ]
        if mismatched:
            sample = mismatched[0]
            return (
                False,
                "",
                f"Config '{resolved}' is a {target_base} configuration, but "
                f"{len(mismatched)} of the selected row(s) are not — e.g. row {sample.index} "
                f"({sample.sample_name}) is {sample.physical_configuration}.\n"
                f"  A config override changes reduction parameters, not the measured geometry.\n"
                f"  Clone the row's own config instead: /config clone "
                f"{sample.physical_configuration} {sample.physical_configuration}_v2",
            )

    return True, resolved, ""


def _no_match_message(table, pattern: str, *, by_config: bool) -> str:
    """Explain a no-match, distinguishing an empty table from a bad pattern.

    An empty working table used to report "no rows with sample name containing
    '<pattern>'", which blamed the pattern for a missing /matchruns.
    """
    if not table.rows:
        return (
            f"Working table '{table.name}' is empty — nothing to set.\n"
            f"  Run /matchruns first (or /table list if you expected rows in another table)."
        )
    if by_config:
        return (
            f"No rows in configuration '{pattern}' in table '{table.name}'.\n"
            f"  Configs here: {', '.join(table.configurations)}"
        )
    names = sorted({r.sample_name for r in table.rows})
    shown = ", ".join(names[:12]) + (f" … (+{len(names) - 12})" if len(names) > 12 else "")
    return (
        f"No rows with sample name matching '{pattern}' in table '{table.name}'.\n"
        f"  Sample names are matched exactly unless you use *, e.g. '*{pattern}*'.\n"
        f"  Samples here: {shown}"
    )


async def handle_set(args: list[str], state: SessionState) -> CommandResult:
    """Handle /set <run> <field> <value> — set a run association on a working table row.

    Run number values are strings (supports comma-separated multi-run like "111, 112").
    Use "none", "null", or "" to clear a value (thickness and sample_name can't be cleared).

    Examples:
        /set 167942 trans 167931
        /set 167942 bkg 167940
        /set 167942 emp 167929
        /set 167942 trans,emp 167931    ← one run as both transmission AND empty beam
        /set 167942 bkg none            ← clears background
        /set 167942 trans "111, 112"    ← multi-run for combined statistics
        /set 167942 thickness 0.1
        /set 167942 sample MyNewName    ← rename the sample on this row
        /set 3 name S3                  ← 'name' is an alias for 'sample'
        /set 4 cfg 4m10a_mask2          ← reassign row 4 to a (cloned) config
        /set 4 cfg none                 ← clear override → use physics-derived config
                                         ('cfg' is canonical; 'config'/'configuration' also work)

    Bulk selectors:
        /set --sample <name> <field> <value>   ← by sample name ('*' = all rows)
        /set --config <id> <field> <value>     ← every row in one configuration,
                                                 e.g. /set --config 4m10a emp 186517
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

    # Bulk set by sample name or by configuration.
    if first in ("--sample", "--config", "--cfg"):
        by_config = first != "--sample"
        selector = "--config" if by_config else "--sample"
        if len(args) < 4:
            if by_config:
                configs = state.current_table.configurations
                return CommandResult(
                    success=False,
                    message="Usage: /set --config <config_id> <field> <value>\n"
                    "  Example: /set --config 4m10a emp 186517\n"
                    "  Sets the field on every row in that configuration.\n"
                    f"  Configs in this table: {', '.join(configs) or '(none — run /matchruns first)'}",
                )
            return CommandResult(
                success=False,
                message="Usage: /set --sample <name> <field> <value>\n"
                "  Example: /set --sample 3b trans 172804\n"
                "  <name> matches the sample name exactly, or use * as a wildcard\n"
                "  ('*' = every row, '*3b*' = any name containing 3b).",
            )

        pattern = args[1]
        field_name = args[2].lower()
        value_str = " ".join(args[3:])

        attr_names, bad = _resolve_fields(field_name)
        if bad:
            return CommandResult(
                success=False,
                message=f"Unknown field: {bad}. Valid fields: {', '.join(SETTABLE_FIELDS.keys())}",
            )

        table = state.current_table

        if by_config:
            # Match the row's parameter config OR its physics config, so
            # "4m10a" still selects rows pointed at a clone like "4m10a_v2".
            matching_rows = [
                r for r in table.rows
                if config_ids_match(r.configuration, pattern)
                or config_ids_match(r.physical_configuration, pattern)
            ]
        else:
            matching_rows = [
                r for r in table.rows if sample_matches(pattern, r.sample_name)
            ]

        if not matching_rows:
            return CommandResult(
                success=False,
                message=_no_match_message(table, pattern, by_config=by_config),
            )

        ok, display, err = _apply_field_set(matching_rows, attr_names, value_str, state)
        if not ok:
            return CommandResult(success=False, message=err)

        label = _field_label(attr_names)
        if display == "(cleared)":
            return CommandResult(
                success=True,
                message=f"Cleared {label} for {len(matching_rows)} row(s) matching "
                f"{selector} {pattern}.",
            )

        if by_config:
            detail = "  Samples: " + ", ".join(
                sorted(set(r.sample_name for r in matching_rows))
            )
        else:
            detail = "  Configs: " + ", ".join(
                sorted(set(r.configuration for r in matching_rows))
            )
        return CommandResult(
            success=True,
            message=f"Set {label}={display} for {len(matching_rows)} row(s) matching "
            f"{selector} {pattern}.\n{detail}",
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

    attr_names, bad = _resolve_fields(field_name)
    if bad:
        return CommandResult(
            success=False,
            message=f"Unknown field: {bad}. Valid fields: {', '.join(SETTABLE_FIELDS.keys())}",
        )

    table = state.current_table

    indices = parse_row_selection(run_id, table)
    target_rows = [r for r in table.rows if r.index in indices]

    if not target_rows:
        return CommandResult(
            success=False,
            message=f"'{run_id}' not found as row index, range, or scattering run in table '{table.name}'.",
        )

    ok, display, err = _apply_field_set(target_rows, attr_names, value_str, state)
    if not ok:
        return CommandResult(success=False, message=err)

    field_label = _field_label(attr_names)
    row_label = f"{len(target_rows)} row(s)" if len(target_rows) > 1 else f"run {run_id} ({target_rows[0].sample_name})"
    if display == "(cleared)":
        return CommandResult(success=True, message=f"Cleared {field_label} for {row_label}.")
    return CommandResult(
        success=True,
        message=f"Set {field_label}={display} for {row_label}.",
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
