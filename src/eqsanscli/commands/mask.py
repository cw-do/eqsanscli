"""/mask — build a detector mask from a run, and see which masks are available.

The mask goes into the folder eqsanscli was started in, named for the
configuration it belongs to (`mask_4m2o5a_186104.nxs`), which is what makes it
discoverable: the resolver in services/instrument_files.py matches a mask to a
configuration by reading the distance and wavelength out of the filename.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from eqsanscli.commands.router import CommandResult
from eqsanscli.models.session_state import SessionState
from eqsanscli.services import mask_service as ms

_USAGE = (
    "Usage: /mask create <run> [options]\n"
    "       /mask list\n"
    "\n"
    "Builds a mask from the run's own detector image: the beam-stop shadow, the\n"
    "low-response bands at the tube ends, and tubes that differ from others in\n"
    "their front/back group. Use a uniformly illuminated run — banjo, flood or\n"
    "empty cell.\n"
    "\n"
    "  --ipts <n>        experiment holding the run (default: the session's)\n"
    "  --outdir <dir>    where to write (default: the current folder)\n"
    "  --beam-scale <f>  multiply the fitted beam radius (default 1.2 = 20% bigger)\n"
    "  --beam-pad <f>    add a margin beyond it, in MILLIMETRES (default 1.0)\n"
    "                    the beam stop is masked as a real circle on the detector;\n"
    "                    one pixel is 4.09 mm along a tube\n"
    "  --no-beam         do not mask the beam stop\n"
    "  --top <n>         force the top band size (default: measured, min 11)\n"
    "  --bottom <n>      force the bottom band size\n"
    "  --band-drop <f>   band edge threshold, fraction of plateau (default 0.5)\n"
    "  --tubes <a,b,c>   mask these tubes explicitly\n"
    "  --tube-sigma <f>  auto-flag threshold, higher is stricter (default 5)\n"
    "  --no-tubes        skip tube detection\n"
    "  --dry-run         report what would be masked; write only the preview PNG\n"
    "\n"
    "Example: /mask create 186104 --ipts 37618\n"
)


def _parse_args(args: list[str]) -> tuple[dict, str]:
    """Returns (options, error)."""
    opts: dict = {
        "ipts": None, "outdir": None, "beam_scale": ms.DEFAULT_BEAM_SCALE,
        "beam_pad": ms.DEFAULT_BEAM_PAD, "band_drop": ms.DEFAULT_BAND_DROP,
        "tube_sigma": ms.DEFAULT_TUBE_SIGMA, "top": None, "bottom": None,
        "tubes": None, "use_beam": True, "use_tubes": True, "dry_run": False,
    }
    floats = {"--beam-scale": "beam_scale", "--beam-pad": "beam_pad",
              "--band-drop": "band_drop", "--tube-sigma": "tube_sigma"}
    ints = {"--top": "top", "--bottom": "bottom"}
    i = 0
    while i < len(args):
        arg = args[i].lower()
        if arg in ("--no-beam", "--nobeam"):
            opts["use_beam"] = False
        elif arg in ("--no-tubes", "--notubes"):
            opts["use_tubes"] = False
        elif arg in ("--dry-run", "--dryrun"):
            opts["dry_run"] = True
        elif arg in floats or arg in ints or arg in ("--ipts", "--outdir", "--tubes"):
            if i + 1 >= len(args):
                return opts, f"{args[i]} needs a value"
            value = args[i + 1]
            i += 1
            try:
                if arg in floats:
                    opts[floats[arg]] = float(value)
                elif arg in ints:
                    opts[ints[arg]] = int(value)
                elif arg == "--tubes":
                    opts["tubes"] = [int(t) for t in value.replace(" ", "").split(",") if t]
                else:
                    opts[arg.lstrip("-")] = value
            except ValueError:
                return opts, f"{args[i - 1]} expects a number, got {value!r}"
        else:
            return opts, f"unknown option: {args[i]}"
        i += 1
    return opts, ""


async def handle_mask(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(success=False, message=_USAGE)
    sub = args[0].lower()
    if sub in ("create", "make", "new"):
        return await _create(args[1:], state)
    if sub in ("list", "show"):
        return await _list(state)
    if sub in ("help", "-h", "--help"):
        return CommandResult(success=True, message=_USAGE)
    return CommandResult(success=False, message=f"Unknown /mask subcommand: {sub}\n\n{_USAGE}")


async def _create(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(success=False, message="Usage: /mask create <run> [options]")
    run = args[0]
    opts, error = _parse_args(args[1:])
    if error:
        return CommandResult(success=False, message=f"{error}\n\n{_USAGE}")

    ipts = opts["ipts"] or state.ipts
    run_file, searched = ms.resolve_run_file(run, ipts)
    if run_file is None:
        return CommandResult(
            success=False,
            message="Could not find that run. Looked in:\n"
            + "".join(f"    {p}\n" for p in searched)
            + ("  Give --ipts <number>, or pass a full path."
               if not ipts else "  Check the run number, or pass a full path."),
        )

    outdir = os.path.abspath(opts["outdir"] or os.getcwd())
    os.makedirs(outdir, exist_ok=True)

    lines = [f"Reading run {run} — {run_file}", "  [dim]Mantid via drtsans; ~10 s[/dim]"]
    image, error = ms.read_run_image(run_file, outdir, drtsans_version=state.drtsans_version)
    if image is None:
        return CommandResult(success=False, message="\n".join(lines + [f"[red]✗ {error}[/red]"]))

    lines.append(
        f"  [green]✓[/green] {image.n_spectra} spectra, {image.total_counts:,.0f} counts — "
        f"{image.distance_m:g} m, {image.wavelength_a:g} Å, {image.frequency_hz} Hz "
        f"→ config [bold]{image.config}[/bold]"
    )
    if image.title:
        lines.append(f"    [dim]{image.title}[/dim]")

    plan = ms.build_plan(
        image.counts, image.x_mm, image.y_mm, beam_scale=opts["beam_scale"], beam_pad=opts["beam_pad"],
        band_drop=opts["band_drop"], tube_sigma=opts["tube_sigma"],
        bottom=opts["bottom"], top=opts["top"], tubes=opts["tubes"],
        use_beam=opts["use_beam"], use_tubes=opts["use_tubes"],
    )
    mask = ms.shapes_to_mask(plan.shapes, image.x_mm, image.y_mm)
    indices = ms.mask_to_indices(mask)
    n = len(indices)
    lines.append(f"  Masking {n} pixels ({100 * n / mask.size:.2f}%): {plan.summary()}")
    if plan.tube_source == "auto" and not plan.tubes:
        lines.append("    [dim]no deviant tubes at this threshold — lower --tube-sigma "
                     "to look harder, or name them with --tubes[/dim]")

    stem = ms.mask_filename(image.distance_m, image.wavelength_a,
                            image.frequency_hz, run).replace(".nxs", "")
    png = ms.render_comparison(image.counts, mask,
                               os.path.join(outdir, f"{stem}_compare.png"), image.x_mm)
    if png:
        lines.append(f"  [green]✓[/green] preview: {png}")
        lines.append("    [dim]check the red overlay covers the beam, the tube ends and "
                     "nothing else[/dim]")

    if opts["dry_run"]:
        lines.append("\n[yellow]--dry-run: no mask file written.[/yellow]")
        return CommandResult(success=True, message="\n".join(lines))

    mask_path = os.path.join(outdir, f"{stem}.nxs")
    lines.append(f"  Writing {mask_path} [dim](Mantid; ~20 s)[/dim]")
    result, error = ms.write_mask(run_file, indices, mask_path, outdir,
                                  drtsans_version=state.drtsans_version)
    if result is None:
        return CommandResult(success=False, message="\n".join(lines + [f"[red]✗ {error}[/red]"]))

    readback = result.get("n_masked_readback")
    if readback != n:
        lines.append(f"  [yellow]⚠ wrote {n} masked pixels but the file reads back "
                     f"{readback}[/yellow]")
    else:
        lines.append(f"  [green]✓[/green] verified: reads back {readback} masked pixels "
                     f"the way drtsans reads it")

    params = {
        "run": str(run), "config": image.config, "source": run_file,
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "created_by": "eqsanscli /mask create",
        "beam_mm": (None if plan.beam is None else {
            "xc": plan.beam.xc, "yc": plan.beam.yc, "radius": plan.beam.radius,
            "npix": plan.beam.npix, "units": "mm"}),
        "beam_scale": opts["beam_scale"], "beam_pad": opts["beam_pad"],
        "bottom": plan.bottom, "top": plan.top, "band_drop": opts["band_drop"],
        "tubes": plan.tubes, "tube_source": plan.tube_source,
        "tube_sigma": None if plan.tube_source == "manual" else opts["tube_sigma"],
        "n_masked": n, "shapes": plan.shapes,
        "mask_nxs": os.path.basename(mask_path),
        "compare_png": os.path.basename(png) if png else None,
    }
    params_path = os.path.join(outdir, f"{stem}.params.json")
    with open(params_path, "w") as fh:
        json.dump(params, fh, indent=2)

    size_mb = os.path.getsize(mask_path) / 1e6
    lines.append(f"  [green]✓[/green] {os.path.basename(mask_path)} ({size_mb:.1f} MB), "
                 f"{os.path.basename(params_path)}")
    lines.append("")
    if os.path.abspath(outdir) == os.path.abspath(os.getcwd()):
        lines.append(f"Named for config [bold]{image.config}[/bold], in the current folder — "
                     f"/matchruns and /instrument will pick it up automatically.")
    else:
        lines.append(f"Written outside the current folder; to use it now: "
                     f"/set config {image.config} maskfilename {mask_path}")
    return CommandResult(success=True, message="\n".join(lines))


async def _list(state: SessionState) -> CommandResult:
    """Masks visible to the resolver, in the order it would prefer them."""
    from eqsanscli.services import instrument_files as ifiles

    lines = ["[bold]Masks discoverable from here[/bold]"]
    found = False
    for location, masks in ifiles.local_masks(ipts=state.ipts):
        label = f"  {location}"
        if not masks:
            lines.append(f"{label} [dim]— no mask*.nxs[/dim]")
            continue
        found = True
        lines.append(label)
        for m in masks:
            bits = []
            if m.distance is not None:
                bits.append(f"{m.distance:g} m")
            if m.wavelength is not None:
                bits.append(f"{m.wavelength:g} Å")
            if m.frame_skip:
                bits.append("frame-skip")
            lines.append(f"      {m.name:<40} {', '.join(bits) or '[dim]no config in name[/dim]'}")

    cycles = ifiles.scan_cycles()
    if cycles:
        cycle_masks = ifiles.cycle_masks(cycles[0])
        lines.append(f"  {os.path.join(cycles[0].path, 'masks')}"
                     + ("" if cycle_masks else " [dim]— none[/dim]"))
        for m in cycle_masks:
            found = True
            lines.append(f"      {m.name:<40} [dim]cycle default[/dim]")

    if not found:
        lines.append("")
        lines.append("No masks anywhere. Build one: /mask create <run>")
    else:
        lines.append("")
        lines.append("[dim]First match wins, and a mask naming a different distance or "
                     "wavelength is never borrowed.[/dim]")
    return CommandResult(success=True, message="\n".join(lines))
