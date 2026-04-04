from __future__ import annotations

import os
import re
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.models.config_id import normalize_config_id
from eqsanscli.services.calibration_service import find_scale_factor, list_references

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


def _parse_config_from_filename(path: str) -> str | None:
    """Extract config ID from an output filename like 'porsil_4m10a_Iq.dat'.

    Returns None if no config pattern is recognized.
    """
    stem = os.path.basename(path)
    # Strip known suffixes
    for suffix in ("_Iq.dat", "_Iq.txt", "_frame_0_Iq.dat", ".dat", ".txt"):
        if stem.endswith(suffix):
            stem = stem[:-len(suffix)]
            break
    # Match patterns like '4m10a', '2.5m2.5a', '8m12a30hz' at end of stem
    m = re.search(r"(\d+\.?\d*m\d+\.?\d*a(?:\d+hz)?)$", stem.lower())
    return m.group(1) if m else None


async def handle_calibrate(args: list[str], state: SessionState) -> CommandResult:
    """
    /calibrate <porsil_file> [--ref NG3|NG7] [--qmin 0.01] [--qmax 0.03] [--applynow]
    /calibrate --list-refs
    """
    if not args:
        return CommandResult(
            success=False,
            message="Usage: /calibrate <porsil_iq_file> [--ref NG3|NG7] [--qmin 0.01] [--qmax 0.03] [--applynow]\n"
            "       /calibrate --list-refs\n"
            "  Compares measured porsil I(Q) against absolute scale reference.\n"
            "  Returns the scale factor (apply via /set config <id> standardabsolutescale <value>)\n"
            "  With --applynow: auto-applies scale factor to the matching config in the working table.",
        )

    if args[0] == "--list-refs":
        refs = list_references()
        lines = ["Available reference standards:"]
        for r in refs:
            lines.append(f"  {r['name']:<8} {r['file']:<30} {'✓' if r['exists'] == 'yes' else '✗'}")
        return CommandResult(success=True, message="\n".join(lines))

    measured_file = args[0]
    if not os.path.exists(measured_file):
        candidate = os.path.join(state.output_directory, measured_file)
        if os.path.exists(candidate):
            measured_file = candidate
        else:
            return CommandResult(
                success=False,
                message=f"File not found: {args[0]}\n  (searched in current dir and {state.output_directory})",
            )

    ref = "NG3"
    qmin = 0.01
    qmax = 0.03
    apply_now = False
    i = 1
    while i < len(args):
        a = args[i].lower()
        if a == "--ref" and i + 1 < len(args):
            i += 1
            ref = args[i]
        elif a == "--qmin" and i + 1 < len(args):
            i += 1
            qmin = float(args[i])
        elif a == "--qmax" and i + 1 < len(args):
            i += 1
            qmax = float(args[i])
        elif a == "--applynow":
            apply_now = True
        i += 1

    try:
        result = find_scale_factor(measured_file, reference=ref, qmin=qmin, qmax=qmax)
    except (ValueError, FileNotFoundError) as e:
        return CommandResult(success=False, message=f"Calibration error: {e}")

    msg = (
        f"[bold]Scale factor: {result.scale_factor:.7f}[/bold]\n"
        f"  Measured: {os.path.basename(result.measured_file)}\n"
        f"  Reference: {os.path.basename(result.reference_file)}\n"
        f"  Q range: [{result.qmin}, {result.qmax}] ({result.n_points} points)"
    )

    if apply_now:
        config_id = _parse_config_from_filename(measured_file)
        if config_id is None:
            msg += (
                f"\n\n  [yellow]⚠ --applynow: could not parse config ID from filename.[/yellow]"
                f"\n  Apply manually: /set config <id> standardabsolutescale {result.scale_factor:.7f}"
            )
        else:
            # Find matching config in the working table (normalized comparison)
            table = state.current_table
            norm_target = normalize_config_id(config_id)
            matched_configs = [
                cfg for cfg in table.configurations
                if normalize_config_id(cfg) == norm_target
            ]
            if not matched_configs:
                # Fall back: apply to the config_id as-is
                matched_configs = [config_id]

            applied = []
            n_rows_modified = 0
            for cfg in matched_configs:
                if cfg not in state.configurations:
                    state.configurations[cfg] = {}
                state.configurations[cfg]["standardabsolutescale"] = result.scale_factor
                applied.append(cfg)
                # Mark "done" rows with this config as "modified"
                for row in table.rows:
                    if row.status == "done" and normalize_config_id(row.configuration) == norm_target:
                        row.status = "modified"
                        n_rows_modified += 1

            msg += (
                f"\n\n  [green]✓ Applied scale factor to config(s): {', '.join(applied)}[/green]"
            )
            if n_rows_modified:
                msg += f"\n  ⚠ {n_rows_modified} row(s) marked as modified — will be re-reduced."
    else:
        msg += (
            f"\n\n  To apply: /set config <config_id> standardabsolutescale {result.scale_factor:.7f}"
            f"\n  Or re-run with --applynow to auto-apply to matching config."
        )

    return CommandResult(success=True, message=msg)
