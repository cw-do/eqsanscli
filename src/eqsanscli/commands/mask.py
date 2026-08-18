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
    "Use a uniformly illuminated run — banjo, flood or empty cell — and check the\n"
    "_compare.png it writes. Three things are masked: the [bold]beam stop[/bold], the\n"
    "low-response [bold]bands[/bold] at both tube ends, and [bold]deviant tubes[/bold]. The run number\n"
    "alone is enough; the archive is searched for it, so /load ipts is not needed.\n"
    "\n"
    "[bold]Common[/bold]\n"
    "  --dry-run              report and preview only, write no mask file\n"
    "  --leak                 also mask direct beam that fell past the stop under\n"
    "                         gravity (always reported; masked only if you ask)\n"
    "  --tubes <a,b,c>        mask these tubes as well — auto-detection is\n"
    "                         whole-tube, so a dead segment averages out\n"
    "  --disc <x>,<y>,<r>     mask a disc, in mm. Repeatable; adds to the rest\n"
    "\n"
    "[bold]Beam stop[/bold]  — sized from a horizontal cut through it: the valley between\n"
    "the flare walls is the stop's diameter. Runs with no flare are sized from the\n"
    "shadow instead. Every mask prints the measurement, scale and pad behind its\n"
    "radius, and the mask is meant to be wider than the visibly dark disc — the\n"
    "ring outside that is penumbra, where the stop still blocks part of the beam.\n"
    "  --beam-scale <f>       grow the measured radius (default 1.0 measured,\n"
    "                         1.2 from a shadow); --beam-pad <f> adds y-pixels\n"
    "  --beam-center <x>,<y>  state the centre in mm, skipping detection\n"
    "  --beam-radius <mm>     state the radius in mm, used verbatim\n"
    "  --no-beam              do not mask the beam stop\n"
    "  --leak-scale <f>       grow the leak discs (implies --leak); 1.3-1.5 takes\n"
    "                         the faint tail below the broad peak\n"
    "\n"
    "[bold]Tube ends and tubes[/bold]\n"
    "  --top <n> / --bottom <n>  how MANY pixels to mask at each end, not indices:\n"
    "                         --bottom 11 masks pixels 0-10. Default: measured —\n"
    "                         where response falls below half the plateau — but\n"
    "                         never below the 11-pixel EQSANS convention, which in\n"
    "                         practice is what applies. An explicit value wins, so\n"
    "                         --top 0 --bottom 0 turns the bands off. --bottom is\n"
    "                         the low-index end — the machine-physics mask tool\n"
    "                         names these the other way round.\n"
    "  --tube-sigma <f>       flag tubes more readily, lower is looser (default 5)\n"
    "  --no-tubes             skip tube detection\n"
    "\n"
    "[bold]Elsewhere[/bold]\n"
    "  --ipts <n>             skip the archive search, or disambiguate\n"
    "  --outdir <dir>         where to write (default: here, which is what makes\n"
    "                         the mask discoverable)\n"
    "\n"
    "[bold]Coordinates are millimetres from the detector centre[/bold], +y up, face\n"
    "x -525..525 and y -521..521 — so --disc 13,-55,48 is 13 mm to one side and\n"
    "55 mm BELOW centre. Not pixels: tube index is not a spatial coordinate. The\n"
    "preview carries mm on the bottom and left, tube and pixel index on the top\n"
    "and right, so either can be read straight off it.\n"
    "\n"
    "[bold]Examples[/bold]\n"
    "  /mask create 186104 --dry-run               look before writing\n"
    "  /mask create 186636 --leak                  add the gravity-dropped beam\n"
    "  /mask create 186104 --tubes 146             add a known-bad tube\n"
    "  /mask create 186104 --beam-radius 30        state the stop yourself\n"
    "  /mask create 186636 --disc 13,-55,60        one disc, your own size\n"
    "\n"
    "[bold]If it looks wrong[/bold], open the _compare.png:\n"
    "  beam mask off-centre   run too dim — use a brighter one, or --beam-center\n"
    "  beam mask too small    no flare walls, so the shadow was used — --beam-radius\n"
    "  a bad tube missed      name it with --tubes; segments average out\n"
    "\n"
    "Writes mask_<config>_<run>.nxs, a _compare.png and a .params.json into the\n"
    "current folder. The configuration in the name is what lets /matchruns and\n"
    "/instrument find the mask on their own. Needs drtsans, like /reduce.\n"
)


def _parse_args(args: list[str]) -> tuple[dict, str]:
    """Returns (options, error)."""
    opts: dict = {
        # None = auto: 1.0 for a ring fit, DEFAULT_BEAM_SCALE for a shadow fit.
        "ipts": None, "outdir": None, "beam_scale": None,
        "beam_pad": ms.DEFAULT_BEAM_PAD,
        "tube_sigma": ms.DEFAULT_TUBE_SIGMA, "top": None, "bottom": None,
        "tubes": None, "use_beam": True, "use_tubes": True, "dry_run": False,
        "beam_center": None, "beam_radius": None, "discs": [], "mask_leaks": False,
        "leak_scale": 1.0,
    }
    floats = {"--beam-scale": "beam_scale", "--leak-scale": "leak_scale",
              "--beam-pad": "beam_pad",
              "--tube-sigma": "tube_sigma",
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
    if opts["leak_scale"] <= 0:
        return opts, f"--leak-scale must be positive, got {opts['leak_scale']:g}"
    if opts["leak_scale"] != 1.0:
        opts["mask_leaks"] = True      # sizing the disc means you want it masked
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
            + "  Check the run number, or pass a full path.",
        )
    found_ipts = ms.ipts_from_path(run_file)

    outdir = os.path.abspath(opts["outdir"] or os.getcwd())
    os.makedirs(outdir, exist_ok=True)

    lines = [f"Reading run {run} — {run_file}"]
    if found_ipts and str(found_ipts) != str(ipts or ""):
        # The archive was searched by run number, the way Mantid does — say which
        # experiment the run turned out to belong to.
        lines.append(f"  [dim]found in IPTS-{found_ipts} by searching the archive[/dim]")
    lines.append("  [dim]Mantid via drtsans; ~10 s[/dim]")
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
        leak_scale=opts["leak_scale"],
        beam_scale=opts["beam_scale"], beam_pad=opts["beam_pad"],
        tube_sigma=opts["tube_sigma"],
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
        below = yc < (plan.beam.yc if plan.beam else 0.0)
        what = ("direct beam that fell past the stop" if below
                else "leak above the stop (rim flare / short-wavelength end)")
        # NB: not `state` -- that is this function's SessionState parameter.
        if plan.leaks_masked and below:
            status = ("masked" if plan.leak_scale == 1.0 else
                      f"masked at r {radius * plan.leak_scale:.0f} mm "
                      f"(--leak-scale {plan.leak_scale:g})")
        else:
            hint = "add --leak, or " if below else ""
            status = (f"[dim]not masked — {hint}--disc "
                      f"{xc:.0f},{yc:.0f},{radius:.0f}[/dim]")
        lines.append(f"    [yellow]•[/yellow] {what} at ({xc:.0f}, {yc:.0f}) mm, "
                     f"r {radius:.0f} mm — {status}")
    if plan.beam is not None:
        lines.append(f"    [dim]{plan.beam.how_sized()}[/dim]")
    if plan.bottom or plan.top:
        lines.append(f"    [dim]{plan.how_banded()}[/dim]")
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
            "core_contrast": round(plan.beam.core_contrast, 3),
            "found_from": plan.beam.source,
            "raw_radius_mm": round(plan.beam.raw_radius, 1),
            "applied_scale": plan.beam.applied_scale,
            "applied_pad_mm": round(plan.beam.applied_pad, 2),
            "valley_width_mm": (round(plan.beam.valley_width, 1)
                                if plan.beam.valley_width else None)}),
        "leaks_mm": [{"xc": round(d[0], 1), "yc": round(d[1], 1), "r": round(d[2], 1)}
                     for d in plan.leaks] or None,
        "leaks_masked": plan.leaks_masked,
        "leak_scale": plan.leak_scale,
        "beam_scale": opts["beam_scale"] if opts["beam_scale"] is not None else "auto",
        "beam_pad": opts["beam_pad"], "beam_pad_units": "y-pixels",
        "bottom": plan.bottom, "top": plan.top, "band_drop": ms.DEFAULT_BAND_DROP,
        "bands_measured": [plan.measured_bottom, plan.measured_top],
        "band_source": plan.band_source,
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
