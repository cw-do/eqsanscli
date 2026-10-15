from __future__ import annotations

import os
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.models.config_id import normalize_config_id
from eqsanscli.services import calibration_service as cal
from eqsanscli.services.calibration_service import find_scale_factor, list_references

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState

_USAGE = (
    "Usage: /calibrate <porsil_iq_file> [--ref NG3|NG7|<file>] [--qmin 0.01] [--qmax 0.03] [--applynow]\n"
    "       /calibrate --list-refs\n"
    "  Compares the measured standard's I(Q) with the absolute-scale reference over\n"
    "  the Q window and reports the factor f, its spread and the neighbouring windows.\n"
    "  With --applynow: sets the config's scale to s0 × f, where s0 is the scale the\n"
    "  standard was reduced with (read from its <name>.json) — correct whatever s0 was.\n"
    "  Every calibration is recorded in calibration_<cfg>.json / .png and\n"
    "  calibration_history.jsonl in the output directory.\n"
    "  2.5 m / 2.5 Å curves start above the default window: use --qmin 0.03 --qmax 0.1."
)


def _parse_config_from_filename(path: str) -> str | None:
    """Config ID from an output filename ('porsil_4m2.5a30hz_frame_0_Iq.dat' → '4m2.5a30hz')."""
    return cal.config_from_filename(path)


def _parse_args(args: list[str]) -> tuple[dict, str | None]:
    """Strict flag parsing: an unknown flag or a bad number is an error, never ignored
    (`--qmax0.05` used to be dropped silently and the default window used)."""
    opts = {"ref": cal.DEFAULT_REFERENCE, "qmin": cal.DEFAULT_QMIN,
            "qmax": cal.DEFAULT_QMAX, "applynow": False}
    i = 0
    while i < len(args):
        a = args[i].lower()
        if a == "--applynow":
            opts["applynow"] = True
        elif a in ("--ref", "--qmin", "--qmax"):
            if i + 1 >= len(args):
                return opts, f"{args[i]} needs a value"
            v = args[i + 1]
            if a == "--ref":
                opts["ref"] = v
            else:
                try:
                    opts[a[2:]] = float(v)
                except ValueError:
                    return opts, f"{args[i]} needs a number, got '{v}'"
            i += 1
        else:
            return opts, f"Unknown argument: {args[i]}"
        i += 1
    if opts["qmin"] >= opts["qmax"]:
        return opts, f"--qmin ({opts['qmin']}) must be below --qmax ({opts['qmax']})"
    return opts, None


def _record_dir(state: SessionState, measured_file: str) -> str:
    out = state.output_directory
    if out and os.path.isdir(out) and os.access(out, os.W_OK):
        return out
    return os.path.dirname(os.path.abspath(measured_file))


async def handle_calibrate(args: list[str], state: SessionState) -> CommandResult:
    """
    /calibrate <porsil_file> [--ref NG3|NG7] [--qmin 0.01] [--qmax 0.03] [--applynow]
    /calibrate --list-refs
    """
    if not args:
        return CommandResult(success=False, message=_USAGE)

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

    opts, err = _parse_args(args[1:])
    if err:
        return CommandResult(success=False, message=f"{err}\n\n{_USAGE}")

    try:
        result = find_scale_factor(measured_file, reference=opts["ref"],
                                   qmin=opts["qmin"], qmax=opts["qmax"])
    except (ValueError, FileNotFoundError) as e:
        return CommandResult(success=False, message=f"Calibration error: {e}")

    from eqsanscli.services import scale_service

    config_id = _parse_config_from_filename(measured_file)
    s0 = cal.scale_reduced_with(measured_file)
    f = result.scale_factor
    lo, hi = result.neighbour_factors
    nb = ", ".join("—" if v is None else f"{v:.5g}" for v in (lo, hi))
    msg = (
        f"[bold]Scale factor f: {f:.7f}[/bold]  (spread {result.std_rel:.1%}, "
        f"{result.n_points} points; neighbouring windows: {nb})\n"
        f"  Measured: {os.path.basename(result.measured_file)}\n"
        f"  Reference: {os.path.basename(result.reference_file)}\n"
        f"  Q range: [{result.qmin}, {result.qmax}]"
    )
    if s0 is None:
        msg += (f"\n  Reduced with scale s0: unknown — {cal.input_json(measured_file).name} "
                f"not found beside the I(Q) file")
    else:
        msg += f"\n  Reduced with scale s0 = {s0:.7g}  →  new scale s0 × f = {s0 * f:.7f}"
    for w in cal.flatness_warnings(result):
        msg += f"\n  [yellow]⚠ {w}[/yellow]"

    applied_cfgs: list[str] = []
    previous = None
    if opts["applynow"]:
        if config_id is None:
            msg += ("\n\n  [yellow]⚠ --applynow: could not tell the configuration from the "
                    "filename. Nothing applied.[/yellow]")
        elif s0 is None:
            msg += ("\n\n  [yellow]⚠ --applynow refused: the factor is relative to the scale the "
                    "standard was reduced with, and that is unknown here. Nothing applied — "
                    "keep the standard's .json beside its I(Q) file, or set the value yourself "
                    "with /set config.[/yellow]")
        else:
            table = state.current_table
            norm_target = normalize_config_id(config_id)
            applied_cfgs = [cfg for cfg in table.configurations
                            if normalize_config_id(cfg) == norm_target] or [config_id]
            new = s0 * f
            n_rows_modified = 0
            for cfg in applied_cfgs:
                previous = scale_service.current_scale(state, cfg)
                state.configurations.setdefault(cfg, {})["standardabsolutescale"] = new
                for row in table.rows:
                    if row.status == "done" and normalize_config_id(row.configuration) == norm_target:
                        row.status = "modified"
                        n_rows_modified += 1
            msg += (f"\n\n  [green]✓ Applied {new:.7f} (= {s0:.7g} × {f:.7f}) to "
                    f"{', '.join(applied_cfgs)}[/green]")
            warn = scale_service.plausibility(new)
            if warn:
                msg += f"\n  [yellow]⚠ {new:.4g} is {warn}[/yellow]"
            if n_rows_modified:
                msg += f"\n  ⚠ {n_rows_modified} row(s) marked as modified — will be re-reduced."
    else:
        target = f"{s0 * f:.7f}" if s0 is not None else "<s0 × f>"
        msg += (f"\n\n  To apply: /calibrate {os.path.basename(measured_file)} --applynow"
                f"   (or /set config {config_id or '<config_id>'} standardabsolutescale {target})")

    payload = cal.calibration_payload(result, config=config_id, porsil_scale=s0,
                                      applied=bool(applied_cfgs), previous_scale=previous)
    try:
        paths = cal.write_record(payload, result, _record_dir(state, measured_file))
        payload["record"] = paths.get("record")
        payload["png"] = paths.get("png")
        msg += f"\n  Recorded: {paths['record']}" + (f" (+ {os.path.basename(paths['png'])})" if paths.get("png") else "")
    except OSError as e:
        msg += f"\n  [yellow]⚠ calibration record not written: {e}[/yellow]"

    for cfg in applied_cfgs:
        scale_service.record(
            state, cfg, "calibrate",
            measured=payload["measured"], measured_name=os.path.basename(payload["measured"]),
            measured_sha256=payload["measured_sha256"],
            reference=payload["reference"], reference_name=os.path.basename(payload["reference"]),
            qmin=result.qmin, qmax=result.qmax, n_points=result.n_points,
            factor=f, std_rel=result.std_rel, porsil_scale_at_calibration=s0,
            record=payload.get("record"),
            physics=scale_service.physics_snapshot(cal.input_json(measured_file)),
        )

    return CommandResult(success=True, message=msg, data=payload)
