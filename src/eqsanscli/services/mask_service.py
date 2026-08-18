"""Build an EQSANS detector mask from a run's own 2D count image.

Self-contained: the geometry below is plain numpy and is computed inside
eqsanscli, so it is unit-testable without Mantid. Only the two steps that
genuinely need Mantid — reading a run's counts, and writing the mask NeXus that
drtsans consumes — are shelled out to the `drtsans` command, the same mechanism
`integrations/drtsans_runner.py` already uses for reductions.

What gets masked, in the spirit of how EQSANS masks have always been made:

1. the **beam stop** — measured from a horizontal and a vertical cut through it
   (the shadow itself only seeds them), with a small margin;
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
#: Applied when only the shadow itself could be measured — a contrast threshold
#: stops short of the true edge, so the fitted disc is grown a little. It is NOT
#: applied when the cuts measured the valley width directly (see
#: `beam_from_cross_cuts`).
DEFAULT_BEAM_SCALE = 1.2
DEFAULT_BEAM_PAD = 1.0
#: Cross cuts. The beam stop is measured the way it is judged by eye: take a
#: horizontal and a vertical cut through it, and the shadow is the valley between
#: the two flanking walls of flare. The wall *summit* is the stop's rim — flare is
#: brightest just clear of the edge — so the valley width, peak to peak, is the
#: stop diameter. Measured this way run 186636 gives 83 mm against a stop the
#: instrument scientist measures at 90 mm, and run 186631 gives 66 mm at 4 m,
#: where the mask made by hand for that cycle is 68 mm across.
#: Half-width of the band of pixels averaged into a cut.
CUT_BAND_MM = 30.0
#: A wall counts as a wall of the valley when the profile rises this much above
#: the valley floor ...
CUT_WALL_MIN_RATIO = 1.5
#: ... and then falls back to this fraction of its summit further out, which is
#: what separates a flare peak from a plain rise onto the detector plateau. A run
#: with no flare (186104 at 2.5 A) rises and stays up, and is sized from the
#: shadow instead.
CUT_WALL_DECAY = 0.6
#: How far out from the floor to look for a wall.
CUT_SEARCH_MM = 160.0
#: A wall's summit is taken as the intensity-weighted centre of the bins within
#: this fraction of its brightest bin, so a broad crest is not read to the bin.
CUT_SUMMIT_LEVEL = 0.8
#: ... over no more than this many bins either side of the brightest one. Without
#: the bound, the vertical cut's lower wall — the gravity-dropped beam, merged
#: with the rim flare and much broader than it — pulls the measured centre 6 mm
#: down the detector.
CUT_SUMMIT_BINS = 2

DEFAULT_BAND_DROP = 0.5
DEFAULT_TUBE_SIGMA = 5.0

#: Floor for the auto-detected edge bands. EQSANS has masked pixels 1-11 and
#: 246-256 (1-based) for years -- see MASKED_PIXELS in the cycle's
#: prepare_sensitivity.py -- so the sensitivity maps already exclude them.
#: Auto-detection may measure a smaller band on a bright run; never go below the
#: convention, only above it.
DEFAULT_MIN_BAND = 11

#: Pixels below `low_frac` x the median count are beam-stop candidates, but never
#: below `min_count` -- on a dim run a fraction of the median is meaninglessly
#: small and Poisson noise floods the candidate set.
#: A beam-stop candidate must be at least this much darker than its own
#: surroundings (0.6 = 1.7x darker). Local, not global: a dim run's Poisson noise
#: dips below any global cut, while a bright halo around the stop lifts the local
#: baseline.
DEFAULT_BEAM_CONTRAST = 0.6

#: No EQSANS beam stop is anywhere near this big. A larger "detection" means the
#: image defeated the finder, so refuse rather than mask a quarter of the
#: detector.
MAX_BEAM_RADIUS_MM = 60.0

#: Above this the core is not meaningfully darker than its surroundings, so
#: there is no shadow to mask -- refuse rather than invent one.
NO_SHADOW_CONTRAST = 0.8

#: A direct-beam leak is this much brighter than its surroundings. Sample
#: scattering near the beam is broad and centred; a leak is a compact, very
#: bright lobe displaced along y.
LEAK_CONTRAST = 3.0

#: Leak search: within this many stop radii in x, and this many mm in y.
LEAK_COLUMN_FACTOR = 4.0
LEAK_SEARCH_MM = 200.0
LEAK_MIN_PIXELS = 10

#: Pixels of rim the ~5-pixel smoothing window trims off a detected lobe.
LEAK_EDGE_PIXELS = 2.0

#: A core shallower than this is not a clean beam stop: the measured radius will
#: under-state the real one, so say so rather than quietly under-masking.
SHALLOW_CORE_CONTRAST = 0.35

#: A tube reading below `dead_frac` of its local baseline is dead; above
#: `hot_frac`, hot. Relative, so it works at any count level.
DEFAULT_DEAD_FRAC = 0.3
DEFAULT_HOT_FRAC = 3.0

#: Tubes are compared with same-group neighbours within this many indices.
TUBE_BASELINE_WINDOW = 16

#: Below this baseline a tube cannot be judged at all: at ~1 count per pixel a
#: dead tube and an unlucky one look identical.
MIN_BASE_FOR_TUBES = 2.0

#: The MAD-based test needs this much signal to be meaningful, and a deviation of
#: at least `TUBE_MIN_DEVIATION`. Gain variation of 10-20% is normal and is what
#: the sensitivity map corrects; masking is for faults.
MIN_BASE_FOR_SIGMA = 20.0
TUBE_MIN_DEVIATION = 0.25

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
    core_contrast: float = 0.0   # how dark the core is vs its surroundings
    source: str = "shadow"       # "cross cut" when the cuts gave centre + size
    valley_width: float = 0.0    # measured valley width, mm (0 when not measured)

    def as_shape(self) -> dict:
        return {"type": "circle_mm", "xc": self.xc, "yc": self.yc, "r": self.radius}


def disc_is_on_detector(xc: float, yc: float, radius: float,
                        x_mm: np.ndarray, y_mm: np.ndarray) -> bool:
    """Does a disc overlap the detector face at all?"""
    nearest_x = min(max(xc, float(x_mm.min())), float(x_mm.max()))
    nearest_y = min(max(yc, float(y_mm.min())), float(y_mm.max()))
    return math.hypot(xc - nearest_x, yc - nearest_y) <= radius


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


def local_contrast(counts: np.ndarray, x_mm: np.ndarray) -> np.ndarray:
    """Each pixel's brightness relative to its own surroundings.

    The image smoothed over ~5 pixels divided by the same smoothed over ~41, in
    physical tube order so neighbours really are neighbours. Values below 1 are
    darker than their surroundings, above 1 brighter.
    """
    from scipy.ndimage import uniform_filter

    order = physical_tube_order(x_mm)
    image = counts[order].astype(float)
    local = uniform_filter(image, size=5, mode="nearest")
    surround = uniform_filter(image, size=41, mode="nearest")
    return (local / np.clip(surround, 1e-9, None))[np.argsort(order)]


def cut_along_y(counts: np.ndarray, x_mm: np.ndarray, y_mm: np.ndarray,
                centre_x: float, band: float) -> tuple[np.ndarray, np.ndarray]:
    """Vertical cut: mean counts per pixel row, over tubes within `band` of x."""
    tube_x, pixel_y = x_mm[:, 0], y_mm[0, :]
    tubes = np.abs(tube_x - centre_x) <= band
    if int(tubes.sum()) < 3:
        return np.empty(0), np.empty(0)
    return pixel_y, counts[tubes, :].mean(axis=0)


def cut_along_x(counts: np.ndarray, x_mm: np.ndarray, y_mm: np.ndarray,
                centre_y: float, band: float) -> tuple[np.ndarray, np.ndarray]:
    """Horizontal cut: mean counts per tube, over pixel rows within `band` of y.

    Sampled per tube rather than binned by position: tubes sit 5.49 mm apart in x
    but their *index* order interleaves packs of four, so binning at the pitch
    aliases — some bins take two tubes and some none, which moved the measured
    centre by 5 mm. One point per tube, ordered by x, has neither problem.
    """
    tube_x, pixel_y = x_mm[:, 0], y_mm[0, :]
    rows = np.abs(pixel_y - centre_y) <= band
    if int(rows.sum()) < 3:
        return np.empty(0), np.empty(0)
    order = np.argsort(tube_x)
    return tube_x[order], counts[:, rows].mean(axis=1)[order]


def _smooth1d(values: np.ndarray, window: int = 3) -> np.ndarray:
    kernel = np.ones(window) / window
    padded = np.pad(values, (window // 2, window // 2), mode="edge")
    return np.convolve(padded, kernel, mode="valid")[:len(values)]


def _summit_centre(positions: np.ndarray, values: np.ndarray, summit_at: int,
                   summit: float) -> float:
    """Where a wall's summit is, to better than one bin.

    The brightest single bin jitters by a bin width (5.5 mm across tubes), which
    moves both the centre and the width; the crest is broad, so its
    intensity-weighted centre is steadier. On run 186636 this is what brings the
    measured centre to (10, 10) rather than (16, 10).
    """
    low = high = summit_at
    while (low - 1 >= 0 and summit_at - (low - 1) <= CUT_SUMMIT_BINS
           and values[low - 1] >= CUT_SUMMIT_LEVEL * summit):
        low -= 1
    while (high + 1 < len(values) and (high + 1) - summit_at <= CUT_SUMMIT_BINS
           and values[high + 1] >= CUT_SUMMIT_LEVEL * summit):
        high += 1
    crest = values[low:high + 1]
    return float(np.average(positions[low:high + 1], weights=crest))


def valley_walls(positions: np.ndarray, values: np.ndarray, seed: float,
                 search: float) -> Optional[tuple[float, float]]:
    """Positions of the two walls flanking the shadow, or None if it has none.

    Anchored ON the seed rather than on the profile minimum, because outside the
    flare the detector plateau is *lower* than the shadow floor — 1 count against
    9 on run 186636 — so the darkest point of the cut is 77 mm away from the stop.
    The shadow is a local dip between two walls, not the darkest place around.

    A wall is taken at its summit, where the flare is brightest, since that is
    where the stop's rim is. A side that rises and stays up is the plateau, not a
    wall, and disqualifies the measurement (the caller then sizes the shadow
    directly).
    """
    if len(positions) < 5:
        return None
    smoothed = _smooth1d(values)
    near = np.abs(positions - seed) <= max(search, 15.0)
    if not near.any():
        return None
    anchor = int(np.arange(len(positions))[near][np.argmin(smoothed[near])])
    floor = float(smoothed[anchor])

    walls = []
    for direction in (-1, +1):
        index, summit, summit_at, decayed = anchor, floor, anchor, False
        while (0 <= index + direction < len(positions)
               and abs(positions[index + direction] - positions[anchor]) < CUT_SEARCH_MM):
            index += direction
            if smoothed[index] > summit:
                summit, summit_at = float(smoothed[index]), index
            elif (smoothed[index] < CUT_WALL_DECAY * summit
                  and abs(positions[index] - positions[anchor]) > 20.0):
                decayed = True
                break
        if not decayed or summit < CUT_WALL_MIN_RATIO * max(floor, 0.5):
            return None
        walls.append(_summit_centre(positions, smoothed, summit_at, summit))
    low, high = sorted(walls)
    return low, high


def beam_from_cross_cuts(
    counts: np.ndarray,
    x_mm: np.ndarray,
    y_mm: np.ndarray,
    seed_x: float,
    seed_y: float,
    seed_radius: float,
    *,
    band: float = CUT_BAND_MM,
) -> Optional[tuple[float, float, float]]:
    """Centre and radius of the beam stop from a vertical and a horizontal cut.

    The procedure an instrument scientist uses by hand, in order:

    1. a **vertical** cut gives the centre of the deep valley -> the centre's y;
    2. a **horizontal** cut through that y gives the centre's x, and
    3. the **horizontal** valley width is the stop's diameter.

    The width is taken from the horizontal cut only. Vertically the shadow is
    encroached on by the direct beam that fell under gravity, which lands inside
    it and makes it read narrow; horizontally nothing moves, so the width there is
    the stop's own.

    Returns (xc, yc, radius) in mm, or None when either cut has no flare walls.
    """
    vertical = cut_along_y(counts, x_mm, y_mm, seed_x, band)
    walls = valley_walls(*vertical, seed_y, seed_radius)
    if walls is None:
        return None
    yc = (walls[0] + walls[1]) / 2.0

    horizontal = cut_along_x(counts, x_mm, y_mm, yc, band)
    walls = valley_walls(*horizontal, seed_x, seed_radius)
    if walls is None:
        return None
    xc = (walls[0] + walls[1]) / 2.0
    return xc, yc, (walls[1] - walls[0]) / 2.0


def find_beam_stop(
    counts: np.ndarray,
    x_mm: np.ndarray,
    y_mm: np.ndarray,
    *,
    scale: Optional[float] = None,
    pad: float = DEFAULT_BEAM_PAD,
    contrast_max: float = DEFAULT_BEAM_CONTRAST,
    max_radius_mm: float = MAX_BEAM_RADIUS_MM,
) -> tuple[Optional[BeamStop], str]:
    """Locate the beam-stop shadow as a circle on the detector face.

    Returns (beam, reason). `beam` is None when nothing credible was found, and
    `reason` then says why — better than emitting a wrong circle, which is what a
    global threshold does on a dim run.

    The shadow is found by **local** contrast: the image smoothed over ~5 pixels
    against the same image smoothed over ~41, so a region counts as shadow when
    it is much darker than *its own surroundings*. A global threshold cannot do
    this job on both kinds of run:

    - a bright banjo (run 186104, median 90 counts) has a core 12x below plateau
      and any threshold finds it;
    - a weak one (run 186631, median 4 counts) has a core only ~2x below
      plateau, sitting inside a bright halo, while Poisson noise puts ~9% of the
      whole detector under the same threshold. A global cut there returns
      thousands of scattered pixels, whose centroid is nowhere near the beam and
      whose count implies a radius of ~70 mm instead of ~25.

    The centroid is then refined onto the main blob (four rounds, as the
    machine-physics mask maker does), and the result is checked for credibility
    before being returned.
    """
    from scipy.ndimage import label

    contrast = local_contrast(counts, x_mm)

    half_w = (x_mm.max() - x_mm.min()) / 2.0
    half_h = (y_mm.max() - y_mm.min()) / 2.0
    x_mid = (x_mm.max() + x_mm.min()) / 2.0
    y_mid = (y_mm.max() + y_mm.min()) / 2.0
    window = ((np.abs(x_mm - x_mid) <= 0.80 * half_w)
              & (np.abs(y_mm - y_mid) <= 0.70 * half_h))

    dark = (contrast < contrast_max) & window
    if int(dark.sum()) < 8:
        return None, (f"no region is more than {1 / contrast_max:.1f}x darker than its "
                      f"surroundings — this run may have no beam stop in view")

    # Largest connected blob whose own centroid lies inside it. Scattered noise
    # never forms a blob at all, and the containment test throws out the *ring*
    # of low contrast that surrounds a bright beam complex: just outside the
    # bright region the 41-pixel surround still includes it, so those pixels read
    # as very dark. On run 186636 that ring was 3804 px spanning 385 x 376 mm and
    # was being chosen over the real 110 px shadow, putting the "beam centre" at
    # the middle of the detector.
    labels, n_blobs = label(dark)
    blob = None
    npix = 0
    for index in range(1, n_blobs + 1):
        candidate = labels == index
        size = int(candidate.sum())
        if size < 8 or size <= npix:
            continue
        cx = float(x_mm[candidate].mean())
        cy = float(y_mm[candidate].mean())
        nearest = int(np.argmin(np.hypot(x_mm - cx, y_mm - cy)))
        if not bool(candidate.ravel()[nearest]):
            continue        # a ring: its centroid is in the hole, not in itself
        blob, npix = candidate, size
    if blob is None:
        return None, ("no compact dark region found — this run may have no beam "
                      "stop in view, or too few counts to see it")

    xs, ys = x_mm[blob], y_mm[blob]
    xc, yc = float(xs.mean()), float(ys.mean())
    pitch = pixel_pitch_y_mm(y_mm)
    for _ in range(4):
        distance = np.hypot(xs - xc, ys - yc)
        keep = distance <= max(float(np.percentile(distance, 80)) * 1.5, 4.0 * pitch)
        if int(keep.sum()) < 5:
            break
        xc, yc = float(xs[keep].mean()), float(ys[keep].mean())

    # Size the shadow from the blob itself: its equal-area radius, or half its
    # longest extent when it is asymmetric -- at long wavelength the leaked beam
    # eats into one side, so the extent is the better guide. Walking outward until
    # a ring "recovers" brightness collapses here, because the rings quickly
    # include the bright lobes flanking the stop: it returned 10 mm for a stop
    # that is 90 mm across.
    extent_x = float(x_mm[blob].max() - x_mm[blob].min())
    extent_y = float(y_mm[blob].max() - y_mm[blob].min())
    radius = max(math.sqrt(npix * pixel_area_mm2(x_mm, y_mm) / math.pi),
                 max(extent_x, extent_y) / 2.0)

    # Prefer the cross cuts: the shadow above is only a seed for them. They put
    # the centre where the valley actually is and take the size from the valley's
    # own width, which is what survives a shadow filled in by halo or by the
    # gravity-dropped beam. On run 186636 the fitted blob sat 14 mm low.
    source, valley_width = "shadow", 0.0
    cuts = beam_from_cross_cuts(counts, x_mm, y_mm, xc, yc, radius)
    if cuts is not None:
        cut_x, cut_y, cut_radius = cuts
        if (math.hypot(cut_x - xc, cut_y - yc) < 2.0 * max(radius, 20.0)
                and 6.0 < cut_radius <= max_radius_mm):
            xc, yc, radius = cut_x, cut_y, cut_radius
            source, valley_width = "cross cut", 2.0 * cut_radius

    # The 1.2 growth compensates a threshold that stops short of the true edge;
    # a measured valley width needs no such fudge. An explicit --beam-scale
    # always wins.
    if scale is None:
        scale = 1.0 if source == "cross cut" else DEFAULT_BEAM_SCALE

    distance = np.hypot(x_mm - xc, y_mm - yc)
    core = distance < max(6.0, 1.5 * pitch)
    core_contrast = float(contrast[core].mean()) if core.any() else 0.0

    if radius > max_radius_mm:
        return None, (f"the darkest region implies a {radius:.0f} mm radius, larger than "
                      f"any EQSANS beam stop — detection is not trustworthy on this image")
    off_centre = math.hypot(xc - x_mid, yc - y_mid)
    if off_centre > 0.6 * min(half_w, half_h):
        return None, (f"the darkest region is {off_centre:.0f} mm from the detector centre, "
                      f"too far out to be the beam stop")

    if core_contrast > NO_SHADOW_CONTRAST and source != "cross cut":
        return None, (f"the darkest region is only {1 / max(core_contrast, 1e-9):.2f}x darker "
                      f"than its surroundings — no beam stop is discernible in this image")

    beam = BeamStop(xc=xc, yc=yc, radius=radius * scale + pad * pitch, npix=npix,
                    core_contrast=core_contrast, source=source,
                    valley_width=valley_width)
    if source == "cross cut":
        return beam, ""      # measured width: the shallow-core caveat is moot
    if core_contrast > SHALLOW_CORE_CONTRAST:
        return beam, (
            f"the shadow is shallow (core only {1 / max(core_contrast, 1e-9):.1f}x darker "
            f"than its surroundings), so its apparent size is smaller than the beam stop "
            f"really is — at long wavelength the halo fills in the penumbra. Check the "
            f"preview, and set --beam-radius <mm> if it is under-masked"
        )
    return beam, ""



def find_direct_beam_leaks(
    counts: np.ndarray,
    x_mm: np.ndarray,
    y_mm: np.ndarray,
    beam: "BeamStop",
    *,
    contrast: Optional[np.ndarray] = None,
) -> list[tuple[float, float, float]]:
    """Bright patches of direct beam that missed the stop, as discs in mm.

    Neutrons fall in flight and the drop goes as the square of the wavelength, so
    across a wavelength band the direct beam lands at a range of heights. A stop
    sized for the middle of the band lets the ends through, and the leakage is
    bright: on run 186636 (9 m, 15 Å) lobes of 350 and 190 counts sat above and
    below an 8-count shadow, against a plateau of 5.

    Returns one (x, y, radius) disc per lobe — the way these are masked by hand —
    or [] when the beam is stopped cleanly. Reporting is the caller's job: whether
    to mask them is a decision for the person looking at the preview.
    """
    from scipy.ndimage import label

    if contrast is None:
        contrast = local_contrast(counts, x_mm)

    near = ((np.abs(x_mm - beam.xc) < LEAK_COLUMN_FACTOR * beam.radius)
            & (np.abs(y_mm - beam.yc) < LEAK_SEARCH_MM))
    bright = (contrast > LEAK_CONTRAST) & near
    if not bright.any():
        return []

    order = physical_tube_order(x_mm)
    labels = label(bright[order])[0][np.argsort(order)]

    discs: list[tuple[float, float, float]] = []
    for index in range(1, int(labels.max()) + 1):
        patch = labels == index
        if int(patch.sum()) < LEAK_MIN_PIXELS:
            continue
        xc = float(x_mm[patch].mean())
        yc = float(y_mm[patch].mean())
        # Contain the patch, then allow for the smoothing window eating its rim:
        # local contrast is computed over ~5 pixels, so near a lobe's edge the
        # average already includes surrounding plateau and the detected patch is
        # about two pixels short all round. A lobe left half-masked is as useless
        # as one not masked at all.
        radius = float(np.hypot(x_mm[patch] - xc, y_mm[patch] - yc).max())
        rim = LEAK_EDGE_PIXELS * math.sqrt(pixel_area_mm2(x_mm, y_mm))
        discs.append((xc, yc, radius + rim))
    return sorted(discs, key=lambda d: d[1])


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
    dead_frac: float = DEFAULT_DEAD_FRAC,
    hot_frac: float = DEFAULT_HOT_FRAC,
    window: int = TUBE_BASELINE_WINDOW,
    min_deviation: float = TUBE_MIN_DEVIATION,
) -> tuple[list[int], str]:
    """Tubes that are dead, hot, or statistically out of line with their peers.

    Returns (tubes, note); `note` explains when the run cannot support the test.

    Three decisions matter here, each learned from a real run:

    **Median, not mean.** A localised feature must not condemn a whole tube. At
    15 Å the halo around the beam stop is broad and bright, and comparing means
    flagged 29 tubes straight across the centre of run 186636 — 22% of the
    detector — because every tube crossing the halo looked anomalous. The median
    along a tube ignores a feature covering a minority of its pixels.

    **A local baseline.** Each tube is compared with nearby tubes of its own
    front/back group (packs of four, see the module docstring), so a gradient
    across the detector is not mistaken for a fault.

    **Relative first, statistical only when counts allow.** A dead tube reads
    zero against a baseline of six and must be caught however dim the run; but a
    MAD-based z-score on tube medians of 0, 1 and 2 counts is meaningless — it
    flagged 34 tubes on a run whose median pixel had 1 count. So the ratio test
    always applies, and the z-test only where the baseline is high enough to be
    informative *and* the deviation is material. Gain variation of 10-20% is
    normal and is what the sensitivity map is for; it is not a masking matter.
    """
    y_hi = N_PIXELS - top if top else N_PIXELS
    usable = counts[:, bottom:y_hi]
    if usable.size == 0:
        return [], "no usable pixels between the edge bands"

    tube = np.median(usable, axis=1).astype(float)
    group = (np.arange(N_TUBES) // TUBE_PACK) % 2
    base = np.empty(N_TUBES)
    for i in range(N_TUBES):
        peers = [tube[j] for j in range(max(0, i - window), min(N_TUBES, i + window + 1))
                 if j != i and group[j] == group[i]]
        base[i] = float(np.median(peers)) if peers else tube[i]

    judgeable = base >= MIN_BASE_FOR_TUBES
    if not judgeable.any():
        return [], (f"tube response is too low to judge (median {np.median(base):.1f} counts "
                    f"per pixel) — dead tubes cannot be told from noise on this run")

    ratio = tube / np.clip(base, 1e-9, None)
    bad = judgeable & ((ratio < dead_frac) | (ratio > hot_frac))

    # Statistical test where the baseline is strong enough for a MAD to mean
    # something, and only for deviations big enough to matter.
    informative = base >= MIN_BASE_FOR_SIGMA
    if int(informative.sum()) > 8:
        residual = (tube - base)[informative]
        mad = float(np.median(np.abs(residual - np.median(residual))))
        if mad > 0:
            z = np.zeros(N_TUBES)
            z[informative] = np.abs((tube - base)[informative]) / (1.4826 * mad)
            bad |= informative & (z > sigma) & (np.abs(ratio - 1.0) > min_deviation)

    note = ""
    if not judgeable.all():
        note = (f"{int((~judgeable).sum())} tube(s) had too little signal to judge")
    return sorted(int(t) for t in np.nonzero(bad)[0]), note


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
    beam_note: str = ""      # why no beam stop was masked, when there is none
    tube_note: str = ""      # when the run cannot support judging tubes
    discs: list = field(default_factory=list)   # extra (x_mm, y_mm, r_mm) discs
    leaks: list = field(default_factory=list)   # direct-beam leak discs found
    leaks_masked: bool = False
    leak_scale: float = 1.0  # --leak-scale, applied to the masked leak discs

    def summary(self) -> str:
        bits = []
        if self.beam:
            bits.append(
                f"beam stop at ({self.beam.xc:.1f}, {self.beam.yc:.1f}) mm, "
                f"r {self.beam.radius:.1f} mm"
            )
            below = [d for d in self.leaks if d[1] < self.beam.yc]
            if below and self.leaks_masked:
                grown = f" x{self.leak_scale:g}" if self.leak_scale != 1.0 else ""
                bits.append(f"{len(below)} gravity-dropped beam disc(s){grown}")
        if self.bottom or self.top:
            bits.append(f"edge bands {self.bottom} bottom / {self.top} top")
        if self.tubes:
            bits.append(f"{len(self.tubes)} tube(s): {', '.join(map(str, self.tubes))}")
        for xc, yc, radius in self.discs:
            bits.append(f"disc at ({xc:g}, {yc:g}) mm, r {radius:g} mm")
        return "; ".join(bits) or "nothing to mask"


def build_plan(
    counts: np.ndarray,
    x_mm: Optional[np.ndarray] = None,
    y_mm: Optional[np.ndarray] = None,
    *,
    beam_scale: Optional[float] = None,   # None = auto, see find_beam_stop
    beam_pad: float = DEFAULT_BEAM_PAD,
    band_drop: float = DEFAULT_BAND_DROP,
    min_band: int = DEFAULT_MIN_BAND,
    tube_sigma: float = DEFAULT_TUBE_SIGMA,
    bottom: Optional[int] = None,
    top: Optional[int] = None,
    tubes: Optional[Sequence[int]] = None,
    use_beam: bool = True,
    use_tubes: bool = True,
    mask_leaks: bool = False,
    leak_scale: float = 1.0,
    beam_center: Optional[tuple[float, float]] = None,
    beam_radius: Optional[float] = None,
    discs: Optional[Sequence[tuple[float, float, float]]] = None,
) -> MaskPlan:
    """Decide what to mask. Explicit arguments override what is measured."""
    plan = MaskPlan()

    if use_beam and x_mm is not None and y_mm is not None:
        if beam_center is not None or beam_radius is not None:
            # Stated by the user: used verbatim, no scale or pad applied, since
            # they are describing the mask they want rather than the shadow.
            measured, _ = find_beam_stop(counts, x_mm, y_mm, scale=1.0, pad=0.0)
            if beam_center is None and measured is None:
                plan.beam_note = ("--beam-radius given but the centre could not be "
                                  "found; add --beam-center <x> <y> in mm")
            else:
                xc, yc = beam_center if beam_center is not None else (measured.xc, measured.yc)
                radius = beam_radius if beam_radius is not None else measured.radius
                plan.beam = BeamStop(xc=xc, yc=yc, radius=radius, npix=0,
                                     core_contrast=measured.core_contrast if measured else 0.0)
                plan.beam_note = "beam stop set explicitly"
        else:
            plan.beam, plan.beam_note = find_beam_stop(
                counts, x_mm, y_mm, scale=beam_scale, pad=beam_pad,
            )
        if plan.beam:
            plan.shapes.append(plan.beam.as_shape())
            # Direct beam that missed the stop is found and reported always;
            # masking it is the user's call, since it costs low-Q coverage.
            plan.leaks = find_direct_beam_leaks(counts, x_mm, y_mm, plan.beam)
            plan.leaks_masked = bool(mask_leaks and plan.leaks)
            if mask_leaks:
                # Only lobes BELOW the stop. Neutrons fall in flight, so the beam
                # that misses the stop is the beam that fell past it; a bright
                # patch above the stop is rim flare or the short-wavelength end of
                # the band, is an arc rather than a blob, and a disc covering it
                # over-masks badly (r 61 mm reaching y +112 on run 186636). It is
                # reported with its own --disc line instead.
                for xc, yc, radius in plan.leaks:
                    if yc < plan.beam.yc:
                        plan.shapes.append({"type": "circle_mm", "xc": xc,
                                            "yc": yc, "r": radius * leak_scale})
            plan.leak_scale = float(leak_scale)

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
        plan.tubes, plan.tube_note = find_deviant_tubes(
            counts, sigma=tube_sigma, bottom=plan.bottom, top=plan.top,
        )
        plan.tube_source = "auto"
    for tube in plan.tubes:
        plan.shapes.append({"type": "rectangle", "x0": float(tube), "y0": 0.0,
                            "x1": float(tube), "y1": float(N_PIXELS - 1)})

    # Extra discs the user asked for, in millimetres on the detector face.
    for xc, yc, radius in (discs or ()):
        plan.discs.append((float(xc), float(yc), float(radius)))
        plan.shapes.append({"type": "circle_mm", "xc": float(xc), "yc": float(yc),
                            "r": float(radius)})
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
    actual appearance, ascending so the plotted axis reads left-to-right.
    """
    if x_mm is None:
        return None
    return np.argsort(x_mm[:, x_mm.shape[1] // 2])


def index_ticks(x_mm: np.ndarray, y_mm: np.ndarray, order: np.ndarray,
                every_tube: int = 16, every_pixel: int = 32
                ) -> tuple[list[float], list[int], list[float], list[int]]:
    """Tick positions in mm and the tube / pixel index sitting at each.

    Positions are looked up from the real geometry rather than computed, because
    tube index is not a linear function of x: the index order interleaves
    sub-banks in packs of four. Pixel index *is* linear in y, but is read the same
    way here so both axes come from one place.
    """
    slots = list(range(0, N_TUBES, every_tube))
    if slots[-1] != N_TUBES - 1:
        slots.append(N_TUBES - 1)
    tube_pos = [float(x_mm[order[slot], 0]) for slot in slots]
    tube_labels = [int(order[slot]) for slot in slots]

    rows = list(range(0, N_PIXELS, every_pixel))
    if rows[-1] != N_PIXELS - 1:
        rows.append(N_PIXELS - 1)
    pixel_pos = [float(y_mm[0, row]) for row in rows]
    return tube_pos, tube_labels, pixel_pos, [int(r) for r in rows]


def build_comparison_figure(counts: np.ndarray, mask: np.ndarray, title: str,
                            x_mm: Optional[np.ndarray] = None,
                            y_mm: Optional[np.ndarray] = None):
    """Raw image beside the same image with the mask overlaid. Returns (fig, axes)
    or (None, None) when matplotlib is unavailable."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None, None

    order = physical_tube_order(x_mm)
    extent = None
    if order is not None:
        counts = counts[order]
        mask = mask[order]
        # Axes in millimetres, so a position read off the picture can be typed
        # straight into --disc or --beam-center.
        extent = (float(x_mm.min()), float(x_mm.max()),
                  float(y_mm.min()), float(y_mm.max())) if y_mm is not None else None
    shown = np.log10(np.clip(counts.T, 1, None))
    fig, axes = plt.subplots(1, 2, figsize=(12, 5.4), constrained_layout=True)
    for ax, panel in zip(axes, ("raw", "mask overlay")):
        ax.imshow(shown, origin="lower", aspect="auto", cmap="viridis", extent=extent)
        ax.set_xlabel("x (mm)" if extent else "tube index")
        ax.set_ylabel("y (mm)" if extent else "pixel")
        ax.set_title(panel)
        if extent is None:
            continue
        # Viewed with tube index ascending left to right, which is how the
        # detector is looked at. Tube 0 sits at +x on this instrument, so the
        # millimetre axis descends across the picture. Only the view is
        # mirrored -- the coordinates are Mantid's and are what --disc and
        # --beam-center are given, so they keep their signs.
        ax.invert_xaxis()
        # Second scale in detector indices: millimetres are what --disc and
        # --beam-center take, tube/pixel indices are what --tubes and --top /
        # --bottom take, and both are read off the same picture.
        tube_pos, tube_labels, pixel_pos, pixel_labels = index_ticks(
            x_mm, y_mm, order)
        top = ax.twiny()
        top.set_xlim(ax.get_xlim())
        top.set_xticks(tube_pos)
        top.set_xticklabels(tube_labels, fontsize=7)
        top.set_xlabel("tube index  (interleaved in packs of 4 — exact at ticks)",
                       fontsize=8)
        right = ax.twinx()
        right.set_ylim(ax.get_ylim())
        right.set_yticks(pixel_pos)
        right.set_yticklabels(pixel_labels, fontsize=7)
        right.set_ylabel("pixel index", fontsize=8)

    overlay = np.zeros(mask.T.shape + (4,))
    overlay[mask.T] = (1.0, 0.0, 0.0, 0.55)
    axes[1].imshow(overlay, origin="lower", aspect="auto", extent=extent)
    if extent is not None:
        axes[1].invert_xaxis()      # imshow resets the limits it was given
    fig.suptitle(title)
    return fig, axes


def render_comparison(counts: np.ndarray, mask: np.ndarray, path: str,
                      x_mm: Optional[np.ndarray] = None,
                      y_mm: Optional[np.ndarray] = None) -> Optional[str]:
    """Write the comparison PNG. Returns the path, or None without matplotlib."""
    title = os.path.basename(path).replace("_compare.png", "")
    fig, _axes = build_comparison_figure(counts, mask, title, x_mm, y_mm)
    if fig is None:
        return None
    import matplotlib.pyplot as plt
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
