"""Build an EQSANS detector mask from a run's own 2D count image.

Self-contained: the geometry below is plain numpy and is computed inside
eqsanscli, so it is unit-testable without Mantid. Only the two steps that
genuinely need Mantid — reading a run's counts, and writing the mask NeXus that
drtsans consumes — are shelled out to the `drtsans` command, the same mechanism
`integrations/drtsans_runner.py` already uses for reductions.

What gets masked, in the spirit of how EQSANS masks have always been made:

1. the **beam stop** — located from the flare ring around it (the shadow itself
   only seeds that fit), with a small margin;
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
#: applied when the flare ring was fitted, because that measures the edge
#: directly (see `fit_flare_ring`).
DEFAULT_BEAM_SCALE = 1.2
DEFAULT_BEAM_PAD = 1.0
#: Flare ring. The beam stop is ringed by scattering brighter than the plateau,
#: and that ring is a far better handle on the stop than the filled-in shadow is:
#: its centre is the stop's centre, and where the flare *begins* is the stop's
#: edge. Pixels this much brighter than their surroundings count as flare.
FLARE_CONTRAST = 1.6
#: Flare is looked for within this distance of the shadow, so that bright
#: scattering elsewhere on the detector cannot join the circle fit — unrestricted,
#: least squares wandered to a centre 187 mm off the face with a 213 mm radius.
FLARE_SEARCH_MM = 150.0
FLARE_MIN_PIXELS = 30
#: The ring must appear in at least this many of the eight octants around the
#: fitted centre — it has to go round the stop. Two bright lobes side by side
#: reach five octants between them and would otherwise pass. Real rings do
#: better: 8/8 on run 186636, 7/8 on 186631.
FLARE_MIN_OCTANTS = 6
#: The stop edge is where the flare starts: this percentile of the ring pixels'
#: distances from the fitted centre. On run 186636 it gives 45.2 mm for a stop
#: measured at 90 mm across.
FLARE_EDGE_PERCENTILE = 5.0

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
    source: str = "shadow"       # "flare ring" when the ring gave centre + size
    ring_radius: float = 0.0     # fitted flare radius, mm (0 when none was found)

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


def _fit_circle(px: np.ndarray, py: np.ndarray) -> tuple[float, float, float]:
    """Least-squares circle through scattered points (the algebraic/Kasa fit)."""
    design = np.column_stack([px, py, np.ones_like(px)])
    solution, *_ = np.linalg.lstsq(design, px ** 2 + py ** 2, rcond=None)
    xc, yc = float(solution[0]) / 2.0, float(solution[1]) / 2.0
    return xc, yc, float(math.sqrt(max(solution[2] + xc ** 2 + yc ** 2, 0.0)))


def fit_flare_ring(
    counts: np.ndarray,
    x_mm: np.ndarray,
    y_mm: np.ndarray,
    seed_x: float,
    seed_y: float,
    seed_radius: float,
    *,
    contrast: Optional[np.ndarray] = None,
) -> Optional[tuple[float, float, float, float, int, int]]:
    """Fit the bright ring around the beam stop; returns centre, edge and ring.

    This is how these masks are judged by eye: the stop is a dark disc ringed by
    a flare of increased intensity, so the ring's centre is the stop's centre and
    the stop is slightly smaller than the ring. It succeeds exactly where
    measuring the shadow fails — at long wavelength the halo and the
    gravity-dropped beam fill the shadow in, but they *are* the ring.

    Returns `(xc, yc, edge_radius, ring_radius, npix, octants)`, or None when no
    credible ring is present (a bright short run at 2.5 A can have none, and then
    the shadow is unambiguous anyway).
    """
    if contrast is None:
        contrast = local_contrast(counts, x_mm)

    seed_distance = np.hypot(x_mm - seed_x, y_mm - seed_y)
    flare = ((contrast > FLARE_CONTRAST)
             & (seed_distance < FLARE_SEARCH_MM)
             & (seed_distance > 0.5 * seed_radius))
    if int(flare.sum()) < FLARE_MIN_PIXELS:
        return None

    px, py = x_mm[flare], y_mm[flare]
    xc, yc, ring = seed_x, seed_y, seed_radius
    for _ in range(5):
        xc, yc, ring = _fit_circle(px, py)
        distance = np.hypot(px - xc, py - yc)
        keep = np.abs(distance - ring) < max(0.30 * ring, 15.0)
        if int(keep.sum()) < 20:
            break
        px, py = px[keep], py[keep]
    if len(px) < FLARE_MIN_PIXELS or not np.isfinite([xc, yc, ring]).all():
        return None

    angle = np.degrees(np.arctan2(py - yc, px - xc)) % 360.0
    octants = len(set((angle // 45).astype(int)))
    if octants < FLARE_MIN_OCTANTS:
        return None

    distance = np.hypot(px - xc, py - yc)
    edge = float(np.percentile(distance, FLARE_EDGE_PERCENTILE))
    return xc, yc, edge, float(ring), int(len(px)), octants


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

    # Prefer the flare ring: the shadow above is only a seed for it. Where both
    # work they agree; where they differ the ring is right, because what fills a
    # shadow in (halo, gravity-dropped beam) leaves the ring alone.
    source, ring_radius = "shadow", 0.0
    ring_fit = fit_flare_ring(counts, x_mm, y_mm, xc, yc, radius, contrast=contrast)
    if ring_fit is not None:
        ring_x, ring_y, ring_edge, ring_radius, _ring_px, _octants = ring_fit
        if (math.hypot(ring_x - xc, ring_y - yc) < 2.0 * max(radius, 20.0)
                and ring_edge <= max_radius_mm):
            xc, yc, radius, source = ring_x, ring_y, ring_edge, "flare ring"

    # The 1.2 growth compensates a threshold that stops short of the true edge;
    # the ring measures that edge, so it is not grown again. An explicit
    # --beam-scale always wins.
    if scale is None:
        scale = 1.0 if source == "flare ring" else DEFAULT_BEAM_SCALE

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

    if core_contrast > NO_SHADOW_CONTRAST and source != "flare ring":
        return None, (f"the darkest region is only {1 / max(core_contrast, 1e-9):.2f}x darker "
                      f"than its surroundings — no beam stop is discernible in this image")

    beam = BeamStop(xc=xc, yc=yc, radius=radius * scale + pad * pitch, npix=npix,
                    core_contrast=core_contrast, source=source, ring_radius=ring_radius)
    if source == "flare ring":
        return beam, ""      # sized from the ring: the shallow-core caveat is moot
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

    def summary(self) -> str:
        bits = []
        if self.beam:
            bits.append(
                f"beam stop at ({self.beam.xc:.1f}, {self.beam.yc:.1f}) mm, "
                f"r {self.beam.radius:.1f} mm"
            )
            if self.leaks and self.leaks_masked:
                bits.append(f"{len(self.leaks)} direct-beam leak disc(s)")
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
                for xc, yc, radius in plan.leaks:
                    plan.shapes.append({"type": "circle_mm", "xc": xc, "yc": yc,
                                        "r": radius})

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


def render_comparison(counts: np.ndarray, mask: np.ndarray, path: str,
                      x_mm: Optional[np.ndarray] = None,
                      y_mm: Optional[np.ndarray] = None) -> Optional[str]:
    """Raw image beside the same image with the mask overlaid. Returns path or None."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return None

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
    fig, axes = plt.subplots(1, 2, figsize=(11, 5), constrained_layout=True)
    for ax, title in zip(axes, ("raw", "mask overlay")):
        ax.imshow(shown, origin="lower", aspect="auto", cmap="viridis", extent=extent)
        ax.set_xlabel("x (mm)" if extent else "tube index")
        ax.set_ylabel("y (mm)" if extent else "pixel")
        ax.set_title(title)
    overlay = np.zeros(mask.T.shape + (4,))
    overlay[mask.T] = (1.0, 0.0, 0.0, 0.55)
    axes[1].imshow(overlay, origin="lower", aspect="auto", extent=extent)
    fig.suptitle(os.path.basename(path).replace("_compare.png", ""))
    fig.savefig(path, dpi=110)
    plt.close(fig)
    return path
