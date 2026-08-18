"""Build an EQSANS detector mask from a run's own 2D count image.

Self-contained: the geometry below is plain numpy and is computed inside
eqsanscli, so it is unit-testable without Mantid. Only the two steps that
genuinely need Mantid — reading a run's counts, and writing the mask NeXus that
drtsans consumes — are shelled out to the `drtsans` command, the same mechanism
`integrations/drtsans_runner.py` already uses for reductions.

What gets masked, in the spirit of how EQSANS masks have always been made:

1. the **beam-stop shadow** — the low-count blob near the detector centre,
   enlarged slightly;
2. the **top and bottom pixel bands**, where response falls away at the tube
   ends (the long-standing convention is pixels 1-11 and 246-256, 1-based);
3. **deviant tubes** — tubes that differ from their neighbours *of the same
   parity*, because front and back tubes stagger by design and that stagger must
   not be mistaken for a fault.

Detector layout, verified against run 186104: 192 tubes × 256 pixels, workspace
index = ``tube * 256 + pixel``. Reshaped that way the mean profile along the
pixel axis shows the characteristic dead ends (edge/mid ≈ 0.23); the transpose
shows no such structure (≈ 0.93), which is how `reshape_counts` self-checks.

**Tube index is not a spatial coordinate.** Measured from the instrument
geometry: pixels step 4.09 mm along a tube (so pixel index *is* linear in y), but
consecutive tube indices are 10.94 mm apart in x while physical neighbours are
5.49 mm apart — the index order interleaves sub-banks in packs of four
(0, 4, 1, 5, 2, 6, 3, 7, 8, 12, …), and x is not monotonic in tube index. A
circle drawn in index space is therefore not a circle on the detector: for run
186104's beam stop it agreed with the true disc only 87%, masking a region
82.6 × 69.5 mm instead of round. The beam stop is consequently masked in
**millimetres**, against the real pixel positions, which Mantid gives us in the
same pass that reads the counts.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

logger = logging.getLogger(__name__)

N_TUBES = 192
N_PIXELS = 256
N_SPECTRA = N_TUBES * N_PIXELS

#: Defaults, chosen to reproduce masks of the kind used in recent cycles.
DEFAULT_BEAM_SCALE = 1.2
DEFAULT_BEAM_PAD = 1.0
DEFAULT_BAND_DROP = 0.5
DEFAULT_TUBE_SIGMA = 5.0

#: Floor for the auto-detected edge bands. EQSANS has masked pixels 1-11 and
#: 246-256 (1-based) for years -- see MASKED_PIXELS in the cycle's
#: prepare_sensitivity.py -- so the sensitivity maps already exclude them.
#: Auto-detection may measure a smaller band on a bright run; never go below the
#: convention, only above it.
DEFAULT_MIN_BAND = 11

#: Front and back tubes alternate in packs of this many. See find_deviant_tubes
#: for the measurement that establishes it.
TUBE_PACK = 4


# --------------------------------------------------------------------------
# Counts
# --------------------------------------------------------------------------

def reshape_counts(flat: np.ndarray) -> np.ndarray:
    """(N_SPECTRA,) spectrum totals -> (tubes, pixels), verified by structure.

    Raises ValueError if the array is not an EQSANS detector image.
    """
    flat = np.asarray(flat, dtype=float).ravel()
    if flat.size != N_SPECTRA:
        raise ValueError(
            f"expected {N_SPECTRA} spectra (192 tubes x 256 pixels), got {flat.size}"
        )
    counts = flat.reshape(N_TUBES, N_PIXELS)
    if _edge_ratio(counts) > _edge_ratio(flat.reshape(N_PIXELS, N_TUBES).T):
        # Ordering is not tube-major; fall back and say so rather than
        # silently masking the wrong pixels.
        logger.warning("Detector counts look pixel-major; using the transpose.")
        counts = flat.reshape(N_PIXELS, N_TUBES).T
    return counts


def _edge_ratio(counts: np.ndarray) -> float:
    """Mean response in the outer 11 pixels vs the middle half. Dead ends -> small."""
    profile = counts.mean(axis=0)
    edge = float(np.concatenate([profile[:11], profile[-11:]]).mean())
    mid = float(profile[len(profile) // 4: 3 * len(profile) // 4].mean())
    return edge / mid if mid else 1.0


# --------------------------------------------------------------------------
# Shapes
# --------------------------------------------------------------------------

@dataclass
class BeamStop:
    """The beam-stop shadow as a circle on the detector face, in millimetres."""

    xc: float          # mm
    yc: float          # mm
    radius: float      # mm
    npix: int

    def as_shape(self) -> dict:
        return {"type": "circle_mm", "xc": self.xc, "yc": self.yc, "r": self.radius}


def pixel_pitch_y_mm(y_mm: np.ndarray) -> float:
    """Spacing between neighbouring pixels along a tube, from the real positions.

    ~4.09 mm on EQ-SANS. This is the unit `--beam-pad` is quoted in, matching the
    machine-physics mask tool, whose `--beam-pad` is likewise in y-pixels.
    """
    return float(np.median(np.abs(np.diff(y_mm[0]))))


def pixel_area_mm2(x_mm: np.ndarray, y_mm: np.ndarray) -> float:
    """Area one pixel covers, from the real positions.

    The active face spans ~1049 x 1042 mm over 192 x 256 pixels, so a pixel is
    ~5.49 mm across a tube and ~4.09 mm along one: not square, which is exactly
    why the beam stop cannot be a circle in index space.
    """
    width = float(x_mm.max() - x_mm.min())
    height = float(y_mm.max() - y_mm.min())
    return (width / (N_TUBES - 1)) * (height / (N_PIXELS - 1))


def find_beam_stop(
    counts: np.ndarray,
    x_mm: np.ndarray,
    y_mm: np.ndarray,
    *,
    scale: float = DEFAULT_BEAM_SCALE,
    pad: float = DEFAULT_BEAM_PAD,
    search_frac: float = 0.5,
) -> Optional[BeamStop]:
    """Locate the beam-stop shadow and describe it as a circle in millimetres.

    Works on the *deficit* (how far each pixel falls below the local plateau)
    inside the central `search_frac` of the detector, so a bright sample or an
    off-centre beam does not drag the result around.

    The result is physical because tube index is not a spatial coordinate (see
    the module docstring), but the knobs keep the units of the machine-physics
    mask tool: `scale` multiplies the fitted radius and `pad` is **in y-pixels**
    (one pixel along a tube, ~4.09 mm), converted here.
    """
    ny, nx = N_PIXELS, N_TUBES
    x0, x1 = int(nx * (1 - search_frac) / 2), int(nx * (1 + search_frac) / 2)
    y0, y1 = int(ny * (1 - search_frac) / 2), int(ny * (1 + search_frac) / 2)
    window = counts[x0:x1, y0:y1]
    if window.size == 0:
        return None

    plateau = float(np.median(window))
    if plateau <= 0:
        return None
    shadow = window < 0.3 * plateau
    npix = int(shadow.sum())
    if npix < 4:
        return None

    xs = x_mm[x0:x1, y0:y1][shadow]
    ys = y_mm[x0:x1, y0:y1][shadow]
    xc, yc = float(xs.mean()), float(ys.mean())
    # Radius from the shadow's AREA: npix * (area per pixel) = pi r^2. Taking a
    # median distance instead would overestimate by sqrt(2) on a filled disc.
    radius = math.sqrt(npix * pixel_area_mm2(x_mm, y_mm) / math.pi)
    pad_mm = pad * pixel_pitch_y_mm(y_mm)
    return BeamStop(xc=xc, yc=yc, radius=radius * scale + pad_mm, npix=npix)


def find_edge_bands(
    counts: np.ndarray, *, drop: float = DEFAULT_BAND_DROP,
) -> tuple[int, int]:
    """Size of the low-response bands at the bottom and top of every tube.

    Returns (bottom, top) as pixel counts: the response profile along a tube
    ramps up from ~0 at each end, and the band is everything below
    `drop` x the plateau median.
    """
    profile = counts.mean(axis=0)
    plateau = float(np.median(profile[len(profile) // 4: 3 * len(profile) // 4]))
    if plateau <= 0:
        return 0, 0
    threshold = drop * plateau

    bottom = 0
    while bottom < len(profile) and profile[bottom] < threshold:
        bottom += 1
    top = 0
    while top < len(profile) and profile[len(profile) - 1 - top] < threshold:
        top += 1
    return bottom, top


def find_deviant_tubes(
    counts: np.ndarray,
    *,
    sigma: float = DEFAULT_TUBE_SIGMA,
    bottom: int = 0,
    top: int = 0,
    beam: Optional[BeamStop] = None,
    x_mm: Optional[np.ndarray] = None,
    y_mm: Optional[np.ndarray] = None,
) -> list[int]:
    """Tubes whose response differs from others in the same front/back group.

    Front and back tubes alternate in **packs of four** on this detector, not
    one by one. Measured on run 186104: grouping by ``(tube // 4) % 2`` gives a
    median absolute deviation of 2.7 counts, against 19.9 for odd/even and 20.1
    for no grouping, and the high/low pattern matches 4-on/4-off across all 192
    tubes exactly. Comparing odd-to-odd leaves the two populations mixed, which
    inflates the spread ~7x and hides every real outlier.

    Deviation is measured in robust units (median absolute deviation). The edge
    bands and the beam shadow are excluded so they cannot dominate the totals.
    """
    y_hi = N_PIXELS - top if top else N_PIXELS
    usable = counts[:, bottom:y_hi].astype(float, copy=True)
    if beam is not None and x_mm is not None and y_mm is not None:
        # Blank a generous disc around the beam -- not whole tubes, or the tubes
        # crossing the beam would have no data left to judge them by. The beam is
        # a physical circle, so this has to be done in millimetres too.
        wide = {"type": "circle_mm", "xc": beam.xc, "yc": beam.yc,
                "r": beam.radius * 2.0}
        blank = shapes_to_mask([wide], x_mm, y_mm)[:, bottom:y_hi]
        usable[blank] = np.nan
    with np.errstate(invalid="ignore"):
        totals = np.nanmean(usable, axis=1)

    flagged: list[int] = []
    groups = (np.arange(N_TUBES) // TUBE_PACK) % 2
    for side in (0, 1):
        idx = np.nonzero(groups == side)[0]
        vals = totals[idx]
        good = np.isfinite(vals)
        if good.sum() < 8:
            continue
        median = float(np.median(vals[good]))
        mad = float(np.median(np.abs(vals[good] - median)))
        if mad <= 0:
            continue
        # 1.4826 * MAD approximates a standard deviation for normal data.
        limit = sigma * 1.4826 * mad
        for tube, value in zip(idx, vals):
            if np.isfinite(value) and abs(value - median) > limit:
                flagged.append(int(tube))
    return sorted(flagged)


# --------------------------------------------------------------------------
# Mask assembly
# --------------------------------------------------------------------------

@dataclass
class MaskPlan:
    """Everything needed to write a mask, and to explain it afterwards."""

    shapes: list[dict] = field(default_factory=list)
    beam: Optional[BeamStop] = None
    bottom: int = 0
    top: int = 0
    tubes: list[int] = field(default_factory=list)
    tube_source: str = "auto"

    def summary(self) -> str:
        bits = []
        if self.beam:
            bits.append(
                f"beam stop at ({self.beam.xc:.1f}, {self.beam.yc:.1f}) mm, "
                f"r {self.beam.radius:.1f} mm"
            )
        if self.bottom or self.top:
            bits.append(f"edge bands {self.bottom} bottom / {self.top} top")
        if self.tubes:
            bits.append(f"{len(self.tubes)} tube(s): {', '.join(map(str, self.tubes))}")
        return "; ".join(bits) or "nothing to mask"


def build_plan(
    counts: np.ndarray,
    x_mm: Optional[np.ndarray] = None,
    y_mm: Optional[np.ndarray] = None,
    *,
    beam_scale: float = DEFAULT_BEAM_SCALE,
    beam_pad: float = DEFAULT_BEAM_PAD,
    band_drop: float = DEFAULT_BAND_DROP,
    min_band: int = DEFAULT_MIN_BAND,
    tube_sigma: float = DEFAULT_TUBE_SIGMA,
    bottom: Optional[int] = None,
    top: Optional[int] = None,
    tubes: Optional[Sequence[int]] = None,
    use_beam: bool = True,
    use_tubes: bool = True,
) -> MaskPlan:
    """Decide what to mask. Explicit arguments override what is measured."""
    plan = MaskPlan()

    if use_beam and x_mm is not None and y_mm is not None:
        plan.beam = find_beam_stop(counts, x_mm, y_mm, scale=beam_scale, pad=beam_pad)
        if plan.beam:
            plan.shapes.append(plan.beam.as_shape())

    auto_bottom, auto_top = find_edge_bands(counts, drop=band_drop)
    plan.bottom = max(auto_bottom, min_band) if bottom is None else int(bottom)
    plan.top = max(auto_top, min_band) if top is None else int(top)
    if plan.bottom > 0:
        plan.shapes.append({"type": "rectangle", "x0": 0.0, "y0": 0.0,
                            "x1": float(N_TUBES - 1), "y1": float(plan.bottom - 1)})
    if plan.top > 0:
        plan.shapes.append({"type": "rectangle", "x0": 0.0,
                            "y0": float(N_PIXELS - plan.top),
                            "x1": float(N_TUBES - 1), "y1": float(N_PIXELS - 1)})

    if tubes is not None:
        plan.tubes = sorted({int(t) for t in tubes})
        plan.tube_source = "manual"
    elif use_tubes:
        plan.tubes = find_deviant_tubes(
            counts, sigma=tube_sigma, bottom=plan.bottom, top=plan.top,
            beam=plan.beam, x_mm=x_mm, y_mm=y_mm,
        )
        plan.tube_source = "auto"
    for tube in plan.tubes:
        plan.shapes.append({"type": "rectangle", "x0": float(tube), "y0": 0.0,
                            "x1": float(tube), "y1": float(N_PIXELS - 1)})
    return plan


def shapes_to_mask(shapes: Sequence[dict], x_mm: Optional[np.ndarray] = None,
                   y_mm: Optional[np.ndarray] = None) -> np.ndarray:
    """Render shapes into a boolean (tubes, pixels) array. True = masked.

    `circle_mm` shapes need the real pixel positions; rectangles are in index
    space (a tube is a tube, and pixel index is linear in y).
    """
    mask = np.zeros((N_TUBES, N_PIXELS), dtype=bool)
    xs = np.arange(N_TUBES)[:, None]
    ys = np.arange(N_PIXELS)[None, :]
    for shape in shapes:
        kind = shape.get("type")
        if kind == "circle_mm":
            if x_mm is None or y_mm is None:
                logger.warning("Skipping the beam circle: no detector positions.")
                continue
            mask |= ((x_mm - float(shape["xc"])) ** 2
                     + (y_mm - float(shape["yc"])) ** 2) <= float(shape["r"]) ** 2
        elif kind == "ellipse":
            rx = max(float(shape["rx"]), 1e-9)
            ry = max(float(shape["ry"]), 1e-9)
            mask |= (((xs - float(shape["xc"])) / rx) ** 2
                     + ((ys - float(shape["yc"])) / ry) ** 2) <= 1.0
        elif kind == "rectangle":
            x0, x1 = sorted((int(round(shape["x0"])), int(round(shape["x1"]))))
            y0, y1 = sorted((int(round(shape["y0"])), int(round(shape["y1"]))))
            mask[max(0, x0):min(N_TUBES, x1 + 1), max(0, y0):min(N_PIXELS, y1 + 1)] = True
        else:
            logger.warning("Ignoring unknown mask shape %r", kind)
    return mask


def mask_to_indices(mask: np.ndarray) -> list[int]:
    """Workspace indices to mask: index = tube * N_PIXELS + pixel."""
    return np.nonzero(mask.reshape(-1))[0].astype(int).tolist()


# --------------------------------------------------------------------------
# Naming
# --------------------------------------------------------------------------

def config_token(distance_m: float, wavelength_a: float, frequency_hz: int) -> str:
    """Config string for a filename: 4m10a, 4m2o5a, 2o5m2o5a, 4m2o5a30hz.

    Decimal points become 'o' — the long-standing EQSANS filename convention,
    and what `instrument_files._parse_mask_tokens` reads back.
    """
    from eqsanscli.models.config_id import make_config_id

    return make_config_id(distance_m, wavelength_a, frequency_hz).replace(".", "o")


def mask_filename(distance_m: float, wavelength_a: float, frequency_hz: int,
                  run: object) -> str:
    """`mask_<config>_<run>.nxs` — self-describing and discoverable.

    The config token is what makes it discoverable: the mask resolver matches a
    file to a configuration by reading distance and wavelength out of the name.
    The run keeps two masks for one configuration from clobbering each other.
    """
    return f"mask_{config_token(distance_m, wavelength_a, frequency_hz)}_{run}.nxs"


# --------------------------------------------------------------------------
# Talking to Mantid
# --------------------------------------------------------------------------
#
# Two steps genuinely need Mantid: reading a run's counts, and writing the mask
# NeXus that drtsans consumes. Both run as generated scripts under the `drtsans`
# command -- the same mechanism integrations/drtsans_runner.py uses to reduce.
# Nothing outside this file is imported by those scripts, and the geometry is
# decided here in numpy so it stays testable without Mantid.

_COUNTS_SCRIPT = '''"""Generated by eqsanscli /mask create -- reads a run's detector image."""
import json
import sys

import numpy as np
from mantid.simpleapi import Integration, LoadEventNexus

run_file, counts_out, meta_out, pos_out = sys.argv[1:5]

ws = LoadEventNexus(Filename=run_file, OutputWorkspace="mask_src", LoadMonitors=False)
integrated = Integration(InputWorkspace=ws, OutputWorkspace="mask_src_i")
counts = np.array([integrated.readY(i)[0] for i in range(integrated.getNumberHistograms())])
np.save(counts_out, counts)

# Real pixel positions in mm. Tube index is not a spatial coordinate on this
# detector, so the beam stop has to be masked against these, not against indices.
detector_info = ws.detectorInfo()
spectrum_info = ws.spectrumInfo()
positions = np.array(
    [[spectrum_info.position(i).X() * 1000.0, spectrum_info.position(i).Y() * 1000.0]
     for i in range(integrated.getNumberHistograms())],
    dtype=np.float32,
)
np.save(pos_out, positions)

run = ws.getRun()


def log(name, default=None):
    try:
        return run.getProperty(name).timeAverageValue()
    except Exception:
        return default


meta = {
    "n_spectra": int(integrated.getNumberHistograms()),
    "total_counts": float(counts.sum()),
    "detector_distance_mm": log("detectorZ"),
    "wavelength": log("wavelength"),
    "frequency": log("frequency", log("speed1")),
    "title": str(ws.getTitle()),
}
with open(meta_out, "w") as fh:
    json.dump(meta, fh, indent=2)
print("counts written:", counts_out)
'''

_APPLY_SCRIPT = '''"""Generated by eqsanscli /mask create -- writes the mask NeXus."""
import json
import sys

from mantid.simpleapi import (
    ExtractMask, Integration, Load, LoadEventNexus, MaskDetectors, SaveNexusProcessed,
)

run_file, indices_json, mask_out, result_out = sys.argv[1:5]

with open(indices_json) as fh:
    indices = json.load(fh)["indices"]

ws = LoadEventNexus(Filename=run_file, OutputWorkspace="mask_ws", LoadMonitors=False)
# Integrate first: the mask only needs detector flags, and an integrated
# workspace saves in megabytes instead of gigabytes.
ws = Integration(InputWorkspace=ws, OutputWorkspace="mask_ws_i")
MaskDetectors(Workspace=ws, WorkspaceIndexList=indices)
SaveNexusProcessed(InputWorkspace=ws, Filename=mask_out)

# Round-trip exactly the way drtsans consumes it, so a file that cannot be read
# back fails here rather than silently during a reduction.
check = Load(Filename=mask_out, OutputWorkspace="mask_check")
extracted = ExtractMask(InputWorkspace=check, OutputWorkspace="mask_only")
try:
    n_masked = int(extracted.NumberOfSpectraMasked)
except AttributeError:
    n_masked = int(sum(1 for i in range(check.getNumberHistograms())
                       if check.getDetector(i).isMasked()))

with open(result_out, "w") as fh:
    json.dump({"mask_file": mask_out, "n_requested": len(indices),
               "n_masked_readback": n_masked}, fh, indent=2)
print("mask written:", mask_out, "masked:", n_masked)
'''


@dataclass
class RunImage:
    """A run's detector image plus the logs that identify its configuration."""

    counts: np.ndarray
    x_mm: np.ndarray
    y_mm: np.ndarray
    n_spectra: int
    total_counts: float
    distance_m: float
    wavelength_a: float
    frequency_hz: int
    title: str

    @property
    def config(self) -> str:
        from eqsanscli.models.config_id import make_config_id

        return make_config_id(self.distance_m, self.wavelength_a, self.frequency_hz)


def resolve_run_file(run: str, ipts: object = None) -> tuple[Optional[str], list[str]]:
    """Locate a run's NeXus file. Returns (path, searched)."""
    if os.path.isabs(run) and os.path.exists(run):
        return run, [run]
    searched: list[str] = []
    candidates: list[str] = []
    if ipts:
        candidates.append(f"/SNS/EQSANS/IPTS-{ipts}/nexus/EQSANS_{run}.nxs.h5")
    candidates.append(os.path.abspath(f"EQSANS_{run}.nxs.h5"))
    for path in candidates:
        searched.append(path)
        if os.path.exists(path):
            return path, searched
    return None, searched


def _run_drtsans(script_body: str, args: Sequence[str], workdir: str,
                 name: str, drtsans_version: str = "default",
                 timeout: int = 3600) -> tuple[bool, str]:
    """Write a generated script into `workdir` and run it under drtsans."""
    import subprocess

    from eqsanscli.integrations.drtsans_runner import get_drtsans_cmd

    script_path = os.path.join(workdir, f"_eqsanscli_{name}.py")
    with open(script_path, "w") as fh:
        fh.write(script_body)
    cmd = get_drtsans_cmd(drtsans_version) + [script_path, *map(str, args)]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except FileNotFoundError:
        return False, ("'drtsans' not found. /mask create needs it for the Mantid "
                       "read and write, the same way /reduce does.")
    except subprocess.TimeoutExpired:
        return False, f"{name} timed out after {timeout}s"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-6:]
        # Leave the script on disk when it fails, so it can be run by hand.
        return False, (f"{name} failed (exit {proc.returncode}); script kept at "
                       f"{script_path}:\n  " + "\n  ".join(tail))
    try:
        os.remove(script_path)
    except OSError:
        pass
    return True, proc.stdout


def read_run_image(run_file: str, workdir: str, *, drtsans_version: str = "default",
                   timeout: int = 3600) -> tuple[Optional[RunImage], str]:
    """Load a run's counts and configuration logs via Mantid."""
    counts_path = os.path.join(workdir, "_eqsanscli_counts.npy")
    meta_path = os.path.join(workdir, "_eqsanscli_meta.json")
    pos_path = os.path.join(workdir, "_eqsanscli_positions.npy")
    ok, message = _run_drtsans(
        _COUNTS_SCRIPT, [run_file, counts_path, meta_path, pos_path], workdir, "read_counts",
        drtsans_version=drtsans_version, timeout=timeout,
    )
    if not ok:
        return None, message
    try:
        flat = np.load(counts_path)
        positions = np.load(pos_path)
        with open(meta_path) as fh:
            meta = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, f"could not read the counts Mantid produced: {exc}"
    if positions.shape != (flat.size, 2):
        return None, (f"detector positions have shape {positions.shape}, "
                      f"expected ({flat.size}, 2)")

    distance_mm = meta.get("detector_distance_mm")
    frequency = meta.get("frequency")
    image = RunImage(
        counts=reshape_counts(flat),
        x_mm=positions[:, 0].reshape(N_TUBES, N_PIXELS).astype(float),
        y_mm=positions[:, 1].reshape(N_TUBES, N_PIXELS).astype(float),
        n_spectra=int(meta.get("n_spectra", flat.size)),
        total_counts=float(meta.get("total_counts", float(flat.sum()))),
        distance_m=round(float(distance_mm) / 1000.0, 3) if distance_mm else 0.0,
        wavelength_a=round(float(meta.get("wavelength") or 0.0), 2),
        frequency_hz=int(round(float(frequency))) if frequency else 60,
        title=str(meta.get("title", "")),
    )
    for temp in (counts_path, meta_path, pos_path):
        try:
            os.remove(temp)
        except OSError:
            pass
    return image, ""


def write_mask(run_file: str, indices: Sequence[int], mask_path: str, workdir: str,
               *, drtsans_version: str = "default",
               timeout: int = 3600) -> tuple[Optional[dict], str]:
    """Write the mask NeXus and verify it reads back the way drtsans reads it."""
    indices_path = os.path.join(workdir, "_eqsanscli_indices.json")
    result_path = os.path.join(workdir, "_eqsanscli_maskresult.json")
    with open(indices_path, "w") as fh:
        json.dump({"indices": list(map(int, indices))}, fh)

    ok, message = _run_drtsans(
        _APPLY_SCRIPT, [run_file, indices_path, mask_path, result_path], workdir,
        "write_mask", drtsans_version=drtsans_version, timeout=timeout,
    )
    if not ok:
        return None, message
    try:
        with open(result_path) as fh:
            result = json.load(fh)
    except (OSError, ValueError) as exc:
        return None, f"mask written but its result file was unreadable: {exc}"
    for temp in (indices_path, result_path):
        try:
            os.remove(temp)
        except OSError:
            pass
    return result, ""


def physical_tube_order(x_mm: Optional[np.ndarray]) -> Optional[np.ndarray]:
    """Tube indices sorted by physical x, for display.

    Index order interleaves sub-banks, so an image plotted against raw tube index
    scrambles the beam stop into stripes. Sorting by x restores the detector's
    actual appearance.
    """
    if x_mm is None:
        return None
    return np.argsort(-x_mm[:, x_mm.shape[1] // 2])


def render_comparison(counts: np.ndarray, mask: np.ndarray, path: str,
                      x_mm: Optional[np.ndarray] = None) -> Optional[str]:
    """Raw image beside the same image with the mask overlaid. Returns path or None."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

    order = physical_tube_order(x_mm)
    if order is not None:
        counts = counts[order]
        mask = mask[order]
    shown = np.log10(np.clip(counts.T, 1, None))
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)
    for ax, title in zip(axes, ("raw", "mask overlay")):
        ax.imshow(shown, origin="lower", aspect="auto", cmap="viridis")
        ax.set_xlabel("tube (physical order)" if order is not None else "tube index")
        ax.set_ylabel("pixel")
        ax.set_title(title)
    overlay = np.zeros(mask.T.shape + (4,))
    overlay[mask.T] = (1.0, 0.0, 0.0, 0.55)
    axes[1].imshow(overlay, origin="lower", aspect="auto")
    fig.suptitle(os.path.basename(path).replace("_compare.png", ""))
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
