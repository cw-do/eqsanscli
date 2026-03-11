from __future__ import annotations

import os
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.services.calibration_service import find_scale_factor, list_references

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


async def handle_calibrate(args: list[str], state: SessionState) -> CommandResult:
    """
    /calibrate <porsil_file> [--ref NG3|NG7] [--qmin 0.01] [--qmax 0.1]
    /calibrate --list-refs
    """
    if not args:
        return CommandResult(
            success=False,
            message="Usage: /calibrate <porsil_iq_file> [--ref NG3|NG7] [--qmin 0.01] [--qmax 0.1]\n"
            "       /calibrate --list-refs\n"
            "  Compares measured porsil I(Q) against absolute scale reference.\n"
            "  Returns the scale factor to apply via /set config <id> standardabsolutescale <value>",
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
    qmax = 0.1
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
        i += 1

    try:
        result = find_scale_factor(measured_file, reference=ref, qmin=qmin, qmax=qmax)
    except (ValueError, FileNotFoundError) as e:
        return CommandResult(success=False, message=f"Calibration error: {e}")

    msg = (
        f"[bold]Scale factor: {result.scale_factor:.7f}[/bold]\n"
        f"  Measured: {os.path.basename(result.measured_file)}\n"
        f"  Reference: {os.path.basename(result.reference_file)}\n"
        f"  Q range: [{result.qmin}, {result.qmax}] ({result.n_points} points)\n"
        f"\n"
        f"  To apply: /set config <config_id> standardabsolutescale {result.scale_factor:.7f}"
    )

    return CommandResult(success=True, message=msg)
