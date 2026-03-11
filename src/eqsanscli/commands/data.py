from __future__ import annotations

import glob
import os
from typing import TYPE_CHECKING

from eqsanscli.commands.router import CommandResult
from eqsanscli.services.plotting_service import PlotOptions, plot_iq, plot_iqxqy

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState


def _parse_plot_args(args: list[str], opts: PlotOptions | None = None) -> tuple[list[str], PlotOptions]:
    files: list[str] = []
    if opts is None:
        opts = PlotOptions()
    i = 0
    while i < len(args):
        a = args[i]
        al = a.lower()

        if al == "--logx":
            opts.logx, opts.logy = True, opts.logy
        elif al == "--logy":
            opts.logy = True
        elif al == "--linx":
            opts.logx = False
        elif al == "--liny":
            opts.logy = False
        elif al == "--loglog":
            opts.logx = opts.logy = True
        elif al == "--linlin":
            opts.logx = opts.logy = False
        elif al == "--kratky":
            opts.kratky = True
            opts.logx = opts.logy = False
        elif al == "--guinier":
            opts.guinier = True
            opts.logx = opts.logy = False
        elif al == "--porod":
            opts.porod = True
            opts.logx = opts.logy = False
        elif al == "--noerror":
            opts.errorbars = False
        elif al == "--grid":
            opts.grid = True
        elif al == "--nolegend":
            opts.legend = False
        elif al == "--xmin" and i + 1 < len(args):
            i += 1; opts.xmin = float(args[i])
        elif al == "--xmax" and i + 1 < len(args):
            i += 1; opts.xmax = float(args[i])
        elif al == "--ymin" and i + 1 < len(args):
            i += 1; opts.ymin = float(args[i])
        elif al == "--ymax" and i + 1 < len(args):
            i += 1; opts.ymax = float(args[i])
        elif al == "--title" and i + 1 < len(args):
            i += 1; opts.title = args[i]
        elif al == "--xlabel" and i + 1 < len(args):
            i += 1; opts.xlabel = args[i]
        elif al == "--ylabel" and i + 1 < len(args):
            i += 1; opts.ylabel = args[i]
        elif al == "--marker" and i + 1 < len(args):
            i += 1; opts.marker = args[i]
        elif al == "--linewidth" and i + 1 < len(args):
            i += 1; opts.linewidth = float(args[i])
        elif al == "--offset" and i + 1 < len(args):
            i += 1; opts.offset_y = float(args[i])
        elif al == "--save" and i + 1 < len(args):
            i += 1; opts.save = args[i]
        elif al == "--dpi" and i + 1 < len(args):
            i += 1; opts.dpi = int(args[i])
        elif al == "--figsize" and i + 2 < len(args):
            i += 1; w = int(args[i])
            i += 1; h = int(args[i])
            opts.figsize = (w, h)
        elif al == "--display" and i + 1 < len(args):
            i += 1; opts.display = args[i].lower()
        elif al == "--colormap" and i + 1 < len(args):
            i += 1; opts.colormap = args[i]
        elif al == "--nosave":
            opts.display = "window"
        elif not a.startswith("--"):
            expanded = glob.glob(a)
            if expanded:
                files.extend(sorted(expanded))
            elif os.path.exists(a):
                files.append(a)
            else:
                files.append(a)
        i += 1

    return files, opts


async def handle_plot(args: list[str], state: SessionState) -> CommandResult:
    if not args:
        return CommandResult(
            success=False,
            message="Usage: /plot <file|pattern> [flags]\n"
            "  1D: --logx --logy --linx --liny --loglog --linlin\n"
            "      --kratky --guinier --porod --noerror --grid\n"
            "      --xmin/xmax/ymin/ymax <val> --offset <factor>\n"
            "  2D: auto-detected from Iqxqy filename --colormap <name>\n"
            "  Display: --display window|save (auto-detects X11)\n"
            "  Output: --save <path> --dpi <val> --title <text>",
        )

    defaults = PlotOptions(
        logx=state.plot_logx,
        logy=state.plot_logy,
        errorbars=state.plot_errorbars,
        figsize=state.plot_figsize,
        dpi=state.plot_dpi,
        linestyle=state.plot_linestyle,
    )

    files, opts = _parse_plot_args(args, defaults)

    resolved = []
    for f in files:
        if os.path.exists(f):
            resolved.append(f)
        elif os.path.exists(os.path.join(state.output_directory, f)):
            resolved.append(os.path.join(state.output_directory, f))
        elif glob.glob(os.path.join(state.output_directory, f)):
            resolved.extend(sorted(glob.glob(os.path.join(state.output_directory, f))))
        else:
            resolved.append(f)
    files = resolved

    missing = [f for f in files if not os.path.exists(f)]
    if missing:
        return CommandResult(
            success=False,
            message=f"Files not found: {', '.join(missing)}\n"
            f"  (searched in current dir and {state.output_directory})\n"
            f"  Use /list iq to see available files.",
        )

    if not files:
        return CommandResult(success=False, message="No files specified. Use /list iq to see available files.")

    try:
        is_2d = any("iqxqy" in os.path.basename(f).lower() for f in files)
        if is_2d:
            result_path = plot_iqxqy(files[0], opts)
            msg = f"2D plot: {os.path.basename(files[0])}"
        else:
            result_path = plot_iq(files, opts)
            msg = f"Plot: {len(files)} file(s)"
    except Exception as e:
        return CommandResult(success=False, message=f"Plot error: {e}")

    if opts.save:
        msg += f"\n  Saved: {result_path}"

    return CommandResult(success=True, message=msg)


async def handle_list_iq(args: list[str], state: SessionState) -> CommandResult:
    output_dir = args[0] if args else state.output_directory
    if not os.path.isdir(output_dir):
        return CommandResult(success=True, message=f"Output directory not found: {output_dir}")

    iq_files = sorted(glob.glob(os.path.join(output_dir, "*_Iq.dat")))
    iq_files += sorted(glob.glob(os.path.join(output_dir, "*_Iq.txt")))
    iq_files += sorted(glob.glob(os.path.join(output_dir, "merged_*_Iq.txt")))
    iq_files = sorted(set(iq_files))

    if not iq_files:
        return CommandResult(success=True, message=f"No I(Q) files in {output_dir}")

    lines = [f"I(Q) files in {output_dir} ({len(iq_files)}):"]
    for f in iq_files:
        size_kb = os.path.getsize(f) / 1024
        lines.append(f"  {os.path.basename(f):<50} {size_kb:.1f} KB")

    lines.append(f"\n[dim]Use /plot <filename> to plot. Files resolve from outputdir automatically.[/dim]")

    return CommandResult(success=True, message="\n".join(lines))


async def handle_list_iqxqy(args: list[str], state: SessionState) -> CommandResult:
    output_dir = args[0] if args else state.output_directory
    if not os.path.isdir(output_dir):
        return CommandResult(success=True, message=f"Output directory not found: {output_dir}")

    files = sorted(glob.glob(os.path.join(output_dir, "*Iqxqy*")))

    if not files:
        return CommandResult(success=True, message=f"No I(Qx,Qy) files in {output_dir}")

    lines = [f"I(Qx,Qy) files in {output_dir} ({len(files)}):"]
    for f in files:
        size_kb = os.path.getsize(f) / 1024
        lines.append(f"  {os.path.basename(f):<50} {size_kb:.1f} KB")

    return CommandResult(success=True, message="\n".join(lines))
