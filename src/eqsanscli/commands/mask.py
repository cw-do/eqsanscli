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
    "[bold]/mask create <run> \\[options][/bold]   build a mask from a run's own detector image\n"
    "[bold]/mask list[/bold]                     masks discoverable from here\n"
    "\n"
    "Use a uniformly illuminated run — banjo, flood or empty cell. Counting\n"
    "statistics matter: ~90 counts/pixel is comfortable, ~4 is marginal. At long\n"
    "wavelength the halo fills the beam-stop penumbra, so a 2.5 Å run gives a\n"
    "cleaner shadow than a 10 Å one.\n"
    "\n"
    "Masks: the beam-stop shadow (found by local contrast, masked as a circle in\n"
    "mm), the low-response bands at both tube ends, and tubes deviating from\n"
    "others in their front/back pack of four.\n"
    "\n"
    "[bold]Where the run comes from[/bold]\n"
    "  --ipts <n>             experiment holding the run (default: the session's)\n"
    "  --outdir <dir>         where to write (default: the current folder, which\n"
    "                         is what makes the mask auto-discoverable)\n"
    "  --dry-run              report + preview PNG only, write no mask file\n"
    "\n"
    "[bold]Beam stop[/bold]\n"
    "  --beam-scale <f>       multiply the fitted radius (default 1.2)\n"
    "  --beam-pad <f>         margin beyond it, in pixels along a tube (default 1.0;\n"
    "                         1 px = 4.09 mm). Radius = fitted x scale + pad.\n"
    "  --beam-center <x>,<y>  state the centre in mm; skips detection\n"
    "  --beam-radius <mm>     state the radius in mm; used verbatim\n"
    "  --no-beam              do not mask the beam stop\n"
    "  --leak                 also mask direct beam that fell under gravity and\n"
    "                         missed the stop (reported either way; see below)\n"
    "\n"
    "[bold]Gravity-dropped direct beam[/bold]\n"
    "  Neutrons fall in flight and the drop goes as the square of the wavelength,\n"
    "  so at long wavelength and long flight path some direct beam misses the stop\n"
    "  and lands above or below it, bright. On a 9 m 15 A run those lobes reached\n"
    "  350 counts against a plateau of 5.\n"
    "  Leaks are always FOUND and REPORTED, with their position and radius, but\n"
    "  masking them costs low-Q coverage, so it is your call: --leak adds one disc\n"
    "  per lobe, or copy the reported numbers into --disc to take just the one you\n"
    "  want.\n"
    "\n"
    "[bold]Extra shapes[/bold]\n"
    "  --disc <x>,<y>,<r>     mask a disc at (x, y) with radius r. Repeatable.\n"
    "\n"
    "  [bold]Coordinates: millimetres from the centre of the detector[/bold], which is\n"
    "  where the undeflected beam hits it. +y is up. The face spans x -525..525 and\n"
    "  y -521..521 mm, so (0,0) is the middle and (13,-55) is 13 mm to one side and\n"
    "  55 mm BELOW centre. Not pixels: tube index is not a spatial coordinate (the\n"
    "  index order interleaves sub-banks), so a disc in index space would not be\n"
    "  round. The _compare.png axes are in these same millimetres, so a position\n"
    "  read off the picture can be typed straight in. --beam-center uses the same\n"
    "  system.\n"
    "\n"
    "[bold]Tube ends[/bold]\n"
    "  --top <n> / --bottom <n>  how MANY pixels to mask at each end (not indices).\n"
    "                         --bottom 11 masks pixels 0-10, --top 11 masks 245-255.\n"
    "                         Default: measured, never below 11 (the long-standing\n"
    "                         EQSANS convention). An explicit value overrides that\n"
    "                         floor, so --top 0 --bottom 0 disables the bands.\n"
    "                         --bottom is the low-pixel-index end, i.e. the bottom\n"
    "                         of the preview image. NOTE the machine-physics mask\n"
    "                         tool names these the other way round.\n"
    "  --band-drop <f>        where a band edge is called, as a fraction of the\n"
    "                         plateau (default 0.5); raise it to mask more\n"
    "\n"
    "[bold]Bad tubes[/bold]\n"
    "  --tubes <a,b,c>        mask these tubes explicitly\n"
    "  --tube-sigma <f>       auto-flag threshold, higher is stricter (default 5).\n"
    "                         Applies only where counts support it and the tube is\n"
    "                         off by >25%; dead (<30% of local baseline) and hot\n"
    "                         (>3x) tubes are caught at any count level.\n"
    "  --no-tubes             skip tube detection\n"
    "\n"
    "[bold]Examples[/bold]\n"
    "  /mask create 186104 --ipts 37618            build it\n"
    "  /mask create 186104 --dry-run               look before writing\n"
    "  /mask create 186104 --beam-radius 30        state the stop yourself\n"
    "  /mask create 186104 --tubes 146             add a known-bad tube\n"
    "  /mask create 186104 --top 12 --bottom 11    set the tube-end bands\n"
    "  /mask create 186104 --disc 120,-80,15       mask a blemish at (120,-80) mm\n"
    "  /mask create 186104 --disc 0,0,25 --disc 120,-80,15    several discs\n"
    "  /mask create 186104 --tube-sigma 3          flag tubes more readily\n"
    "\n"
    "[bold]If it looks wrong[/bold] — always open the _compare.png first:\n"
    "  too big / off-centre   the run is too dim; use a brighter one, or give\n"
    "                         --beam-center and --beam-radius\n"
    "  too small              long wavelength fills the penumbra (you are warned);\n"
    "                         set --beam-radius\n"
    "  bad tube not flagged   auto-detection is whole-tube, so a dead *segment*\n"
    "                         averages out; name it with --tubes\n"
    "\n"
    "Writes mask_<config>_<run>.nxs, a _compare.png and a .params.json. The\n"
    "configuration comes from the run's own logs, and the filename is what makes\n"
    "the mask discoverable, so /matchruns and /instrument pick it up on their own.\n"
    "Needs drtsans for the Mantid read and write, like /reduce.\n"
)


def _parse_args(args: list[str]) -> tuple[dict, str]:
    """Returns (options, error)."""
    opts: dict = {
        "ipts": None, "outdir": None, "beam_scale": ms.DEFAULT_BEAM_SCALE,
        "beam_pad": ms.DEFAULT_BEAM_PAD, "band_drop": ms.DEFAULT_BAND_DROP,
        "tube_sigma": ms.DEFAULT_TUBE_SIGMA, "top": None, "bottom": None,
        "tubes": None, "use_beam": True, "use_tubes": True, "dry_run": False,
        "beam_center": None, "beam_radius": None, "discs": [], "mask_leaks": False,
    }
    floats = {"--beam-scale": "beam_scale", "--beam-pad": "beam_pad",
              "--band-drop": "band_drop", "--tube-sigma": "tube_sigma",
              "--beam-radius": "beam_radius"}
    ints = {"--top": "top", "--bottom": "bottom"}
    i = 0
    while i < len(args):
        arg = args[i].lower()
        if arg in ("--no-beam", "--nobeam"):
            opts["use_beam"] = False
        elif arg in ("--leak", "--leaks", "--mask-leak"):
            opts["mask_leaks"] = True
        elif arg in ("--no-tubes", "--notubes"):
            opts["use_tubes"] = False
        elif arg in ("--dry-run", "--dryrun"):
            opts["dry_run"] = True
        elif arg in floats or arg in ints or arg in ("--ipts", "--outdir", "--tubes",
                                                    "--beam-center", "--disc"):
            if i + 1 >= len(args):
                return opts, f"{args[i]} needs a value"
            value = args[i + 1]
            i += 1
            try:
                if arg in floats:
                    opts[floats[arg]] = float(value)
                elif arg in ints:
                    opts[ints[arg]] = int(value)
                elif arg == "--disc":
                    parts = value.replace(" ", "").split(",")
                    if len(parts) != 3:
                        return opts, "--disc needs <x>,<y>,<radius> in mm"
                    disc = tuple(float(v) for v in parts)
                    if disc[2] <= 0:
                        return opts, "--disc radius must be positive"
                    opts["discs"].append(disc)
                elif arg == "--beam-center":
                    parts = value.replace(" ", "").split(",")
                    if len(parts) != 2:
                        return opts, "--beam-center needs <x>,<y> in mm"
                    opts["beam_center"] = (float(parts[0]), float(parts[1]))
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
        image.counts, image.x_mm, image.y_mm,
        beam_center=opts["beam_center"], beam_radius=opts["beam_radius"],
        discs=opts["discs"], mask_leaks=opts["mask_leaks"],
        beam_scale=opts["beam_scale"], beam_pad=opts["beam_pad"],
        band_drop=opts["band_drop"], tube_sigma=opts["tube_sigma"],
        bottom=opts["bottom"], top=opts["top"], tubes=opts["tubes"],
        use_beam=opts["use_beam"], use_tubes=opts["use_tubes"],
    )
    for disc in opts["discs"]:
        if not ms.disc_is_on_detector(*disc, image.x_mm, image.y_mm):
            lines.append(f"  [yellow]⚠[/yellow] --disc {disc[0]:g},{disc[1]:g},{disc[2]:g} lies off "
                         f"the detector (x {image.x_mm.min():.0f}..{image.x_mm.max():.0f}, "
                         f"y {image.y_mm.min():.0f}..{image.y_mm.max():.0f} mm) — masks nothing")
    mask = ms.shapes_to_mask(plan.shapes, image.x_mm, image.y_mm)
    indices = ms.mask_to_indices(mask)
    n = len(indices)
    lines.append(f"  Masking {n} pixels ({100 * n / mask.size:.2f}%): {plan.summary()}")
    for xc, yc, radius in plan.leaks:
        side = "above" if yc > (plan.beam.yc if plan.beam else 0) else "below"
        # NB: not `state` -- that is this function's SessionState parameter.
        status = "masked" if plan.leaks_masked else (
            f"[dim]not masked — add --leak, or --disc {xc:.0f},{yc:.0f},{radius:.0f}[/dim]")
        lines.append(f"    [yellow]•[/yellow] direct-beam leak {side} the stop at "
                     f"({xc:.0f}, {yc:.0f}) mm, r {radius:.0f} mm — {status}")
    if plan.beam_note and plan.beam_note != "beam stop set explicitly":
        marker = "[yellow]⚠[/yellow]" if plan.beam else "[yellow]⚠ no beam stop masked:[/yellow]"
        lines.append(f"    {marker} {plan.beam_note}")
    if plan.tube_note:
        lines.append(f"    [yellow]⚠[/yellow] {plan.tube_note}")
    elif plan.tube_source == "auto" and not plan.tubes:
        lines.append("    [dim]no deviant tubes at this threshold — lower --tube-sigma "
                     "to look harder, or name them with --tubes[/dim]")

    stem = ms.mask_filename(image.distance_m, image.wavelength_a,
                            image.frequency_hz, run).replace(".nxs", "")
    png = ms.render_comparison(image.counts, mask,
                               os.path.join(outdir, f"{stem}_compare.png"),
                               image.x_mm, image.y_mm)
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
            "npix": plan.beam.npix, "units": "mm",
            "core_contrast": round(plan.beam.core_contrast, 3)}),
        "leaks_mm": [{"xc": round(d[0], 1), "yc": round(d[1], 1), "r": round(d[2], 1)}
                     for d in plan.leaks] or None,
        "leaks_masked": plan.leaks_masked,
        "beam_scale": opts["beam_scale"],
        "beam_pad": opts["beam_pad"], "beam_pad_units": "y-pixels",
        "bottom": plan.bottom, "top": plan.top, "band_drop": opts["band_drop"],
        "band_convention": ("pixel counts at each end; bottom = low pixel index (-y). "
                            "The machine-physics tool names these the other way round."),
        "tubes": plan.tubes, "tube_source": plan.tube_source,
        "discs_mm": [{"xc": d[0], "yc": d[1], "r": d[2]} for d in plan.discs] or None,
        "tube_note": plan.tube_note or None,
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
