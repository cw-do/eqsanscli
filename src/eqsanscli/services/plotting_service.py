"""Plotting service — generates plot scripts and runs them in a subprocess.

Plots open in a separate process so the TUI is never blocked.
PNG is only saved when --save is explicitly provided.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PlotOptions:
    logx: bool = True
    logy: bool = True
    errorbars: bool = True
    xmin: float | None = None
    xmax: float | None = None
    ymin: float | None = None
    ymax: float | None = None
    xlabel: str | None = None
    ylabel: str | None = None
    title: str | None = None
    legend: bool = True
    grid: bool = False
    marker: str | None = None
    linewidth: float = 1.0
    figsize: tuple[int, int] = (10, 7)
    dpi: int = 150
    offset_y: float | None = None
    save: str | None = None
    kratky: bool = False
    guinier: bool = False
    porod: bool = False
    linestyle: str = "line+marker"
    display: str = "window"
    colormap: str = "jet"


def load_iq_native(filename: str) -> SimpleNamespace:
    data = np.loadtxt(filename, comments="#")
    if data.ndim == 1:
        data = data.reshape(1, -1)
    return SimpleNamespace(
        mod_q=data[:, 0],
        intensity=data[:, 1],
        error=data[:, 2] if data.shape[1] > 2 else None,
        dq=data[:, 3] if data.shape[1] > 3 else None,
    )


def _opts_to_dict(options: PlotOptions) -> dict:
    return {
        "logx": options.logx,
        "logy": options.logy,
        "errorbars": options.errorbars,
        "xmin": options.xmin,
        "xmax": options.xmax,
        "ymin": options.ymin,
        "ymax": options.ymax,
        "xlabel": options.xlabel,
        "ylabel": options.ylabel,
        "title": options.title,
        "legend": options.legend,
        "grid": options.grid,
        "marker": options.marker,
        "linewidth": options.linewidth,
        "figsize": list(options.figsize),
        "dpi": options.dpi,
        "offset_y": options.offset_y,
        "save": options.save,
        "kratky": options.kratky,
        "guinier": options.guinier,
        "porod": options.porod,
        "linestyle": options.linestyle,
        "colormap": options.colormap,
    }


# This script is written to a temp file and run as a subprocess.
# It receives files and options as JSON via argv.
_PLOT_SCRIPT = r"""
import sys, json, numpy as np
from pathlib import Path

args = json.loads(sys.argv[1])
files = args["files"]
opts = args["opts"]
plot_type = args["type"]

import matplotlib
matplotlib.use("TkAgg")
import matplotlib.pyplot as plt

if plot_type == "2d":
    from matplotlib.colors import LogNorm
    filename = files[0]
    rows = []
    with open(filename) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            try:
                vals = [float(x) for x in line.split()]
                if len(vals) >= 3:
                    rows.append(vals)
            except ValueError:
                continue
    data = np.array(rows)
    qx, qy, intensity = data[:,0], data[:,1], data[:,2]
    qx_unique, qy_unique = np.unique(qx), np.unique(qy)
    grid = np.full((len(qy_unique), len(qx_unique)), np.nan)
    qx_idx = {v:i for i,v in enumerate(qx_unique)}
    qy_idx = {v:i for i,v in enumerate(qy_unique)}
    for k in range(len(qx)):
        ix, iy = qx_idx.get(qx[k]), qy_idx.get(qy[k])
        if ix is not None and iy is not None:
            grid[iy, ix] = intensity[k]
    fig, ax = plt.subplots(figsize=tuple(opts.get("figsize", [10,7])))
    masked = np.ma.masked_where((grid <= 0) | np.isnan(grid), grid)
    if opts.get("logy", True):
        vmin = np.nanmin(masked[masked > 0]) if np.any(masked > 0) else 1e-3
        vmax = np.nanmax(masked) if np.any(np.isfinite(masked)) else 1.0
        norm = LogNorm(vmin=vmin, vmax=vmax)
    else:
        norm = None
    im = ax.pcolormesh(qx_unique, qy_unique, masked, cmap=opts.get("colormap","jet"), norm=norm, shading="auto")
    fig.colorbar(im, ax=ax, label=r"$I(Q_x, Q_y)$ (cm$^{-1}$)")
    ax.set_xlabel(opts.get("xlabel") or r"$Q_x$ ($\AA^{-1}$)")
    ax.set_ylabel(opts.get("ylabel") or r"$Q_y$ ($\AA^{-1}$)")
    ax.set_aspect("equal")
    ax.set_title(opts.get("title") or Path(filename).stem)
else:
    fig, ax = plt.subplots(figsize=tuple(opts.get("figsize", [5,4])))
    for i, fname in enumerate(files):
        data = np.loadtxt(fname, comments="#")
        if data.ndim == 1:
            data = data.reshape(1, -1)
        q, intensity = data[:,0], data[:,1]
        error = data[:,2] if data.shape[1] > 2 else None
        label = Path(fname).stem
        if opts.get("kratky"):
            x, y, dy = q, q**2 * intensity, None
        elif opts.get("guinier"):
            mask = intensity > 0
            x, y, dy = q[mask]**2, np.log(intensity[mask]), None
        elif opts.get("porod"):
            x, y, dy = q, intensity * q**4, None
        else:
            x, y, dy = q, intensity, error
        offset = opts.get("offset_y")
        if offset and i > 0:
            factor = offset**i
            y = y * factor
            label += f" (x{factor:.0e})"
        ls = opts.get("linestyle", "line+marker")
        lw = opts.get("linewidth", 1)
        mk = "o" if "marker" in ls else None
        ms = 3 if mk else 0
        if ls == "marker":
            lw = 0
        if opts.get("errorbars", True) and dy is not None:
            fmt_str = ("o" if mk else "") + ("-" if "line" in ls else "")
            ax.errorbar(x, y, yerr=dy, label=label, markersize=ms, linewidth=lw, fmt=fmt_str or "o-", capsize=0)
        else:
            ax.plot(x, y, label=label, linewidth=lw, marker=mk, markersize=ms)
    if opts.get("logx", True): ax.set_xscale("log")
    if opts.get("logy", True): ax.set_yscale("log")
    xmin, xmax = opts.get("xmin"), opts.get("xmax")
    ymin, ymax = opts.get("ymin"), opts.get("ymax")
    if xmin is not None or xmax is not None: ax.set_xlim(xmin, xmax)
    if ymin is not None or ymax is not None: ax.set_ylim(ymin, ymax)
    xlabel = opts.get("xlabel")
    ylabel = opts.get("ylabel")
    if not xlabel:
        xlabel = r"$Q^2$ ($\AA^{-2}$)" if opts.get("guinier") else r"$Q$ ($\AA^{-1}$)"
    if not ylabel:
        if opts.get("kratky"): ylabel = r"$Q^2 \times I(Q)$"
        elif opts.get("guinier"): ylabel = r"$\ln\, I(Q)$"
        elif opts.get("porod"): ylabel = r"$I(Q) \times Q^4$"
        else: ylabel = r"$I(Q)$ (cm$^{-1}$)"
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    title = opts.get("title")
    if not title:
        if len(files) == 1:
            title = Path(files[0]).stem
        else:
            title = ", ".join(Path(f).stem for f in files[:3])
            if len(files) > 3:
                title += f" (+{len(files)-3} more)"
    ax.set_title(title)
    if opts.get("legend", True) and len(files) > 1: ax.legend(loc="best", fontsize="small")
    if opts.get("grid"): ax.grid(True, alpha=0.3)

plt.tight_layout()
save_path = opts.get("save")
if save_path:
    fig.savefig(save_path, dpi=opts.get("dpi", 150))
    print(f"Saved: {save_path}")
plt.show()
"""


def _get_python() -> str:
    return sys.executable


def plot_iq(filenames: list[str], options: PlotOptions | None = None) -> str:
    options = options or PlotOptions()
    return _run_plot_subprocess(filenames, options, "1d")


def plot_iqxqy(filename: str, options: PlotOptions | None = None) -> str:
    options = options or PlotOptions()
    return _run_plot_subprocess([filename], options, "2d")


def _run_plot_subprocess(files: list[str], options: PlotOptions, plot_type: str) -> str:
    script_path = os.path.join(tempfile.gettempdir(), "eqsanscli_plot_script.py")
    with open(script_path, "w") as f:
        f.write(_PLOT_SCRIPT)

    payload = json.dumps({"files": files, "opts": _opts_to_dict(options), "type": plot_type})

    subprocess.Popen(
        [_get_python(), script_path, payload],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    return options.save or "(window)"


def _default_xlabel_1d(options: PlotOptions) -> str:
    if options.guinier:
        return r"$Q^2$ ($\AA^{-2}$)"
    return r"$Q$ ($\AA^{-1}$)"


def _default_ylabel_1d(options: PlotOptions) -> str:
    if options.kratky:
        return r"$Q^2 \times I(Q)$ ($\AA^{-2}$ cm$^{-1}$)"
    elif options.guinier:
        return r"$\ln\, I(Q)$"
    elif options.porod:
        return r"$I(Q) \times Q^4$ ($\AA^{-4}$ cm$^{-1}$)"
    return r"$I(Q)$ (cm$^{-1}$)"
