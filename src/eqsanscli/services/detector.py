"""EQSANS detector geometry and image primitives.

Everything here is about the **detector**, not about masks: how a flat spectrum
array becomes a 2D image, where each pixel physically is, and how to read a
profile across the face. Plain numpy, so it is testable without Mantid, and free
of any policy about what should be masked or reduced — algorithms build on top of
it (`mask_service.py` is the first).

**Tube index is not a spatial coordinate.** Measured from the instrument
geometry: pixels step 4.09 mm along a tube (so pixel index *is* linear in y), but
consecutive tube indices are 10.94 mm apart in x while physical neighbours are
5.49 mm apart — the index order interleaves sub-banks in packs of four
(0, 4, 1, 5, 2, 6, 3, 7, 8, 12, ...), and x is not monotonic in tube index. A
circle drawn in index space is therefore not a circle on the detector: for run
186104's beam stop it agreed with the true disc only 87%. Anything spatial is
computed in **millimetres** against the real pixel positions, which Mantid gives
in the same pass that reads the counts.

Detector layout, verified against run 186104: 192 tubes x 256 pixels, workspace
index = ``tube * 256 + pixel``. Reshaped that way the mean profile along the
pixel axis shows the characteristic dead ends (edge/mid ~ 0.23); the transpose
shows no such structure (~ 0.93), which is how `reshape_counts` self-checks.
"""

from __future__ import annotations

import logging
import math
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)

N_TUBES = 192
N_PIXELS = 256
N_SPECTRA = N_TUBES * N_PIXELS
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
#: Front and back tubes alternate in packs of this many. See find_deviant_tubes
#: for the measurement that establishes it.
TUBE_PACK = 4
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
