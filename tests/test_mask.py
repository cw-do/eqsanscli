"""Mask geometry — pure numpy, no Mantid needed.

The Mantid-facing halves (reading a run's counts, writing the NeXus) are
exercised by actually running `/mask create` against a real run; what is tested
here is the part that decides *what* to mask, on a synthetic detector whose
answers are known.

    python tests/test_mask.py
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from eqsanscli.services import mask_service as ms

TRUE_BEAM_X, TRUE_BEAM_Y, TRUE_BEAM_R = 91.0, 131.0, 6.0
# Real geometry, measured from the EQ-SANS instrument definition.
PIXEL_PITCH_MM = 4.09      # along a tube
TUBE_PITCH_MM = 5.493      # between physical neighbours
TRUE_BAND = 11
DEAD_TUBE = 57


def synthetic_positions() -> tuple[np.ndarray, np.ndarray]:
    """Real detector layout: y linear in pixel index, x interleaved in packs of 4.

    Physical order by x is 0, 4, 1, 5, 2, 6, 3, 7, 8, 12, ... so tube index is
    NOT a spatial coordinate — the property that makes an index-space circle
    wrong.
    """
    order = np.empty(ms.N_TUBES, dtype=int)
    slot = 0
    for block in range(0, ms.N_TUBES, 8):
        for offset in range(ms.TUBE_PACK):
            for pack in (0, 1):
                tube = block + pack * ms.TUBE_PACK + offset
                if tube < ms.N_TUBES:
                    order[tube] = slot
                    slot += 1
    x = (order - (ms.N_TUBES - 1) / 2.0) * TUBE_PITCH_MM
    y = (np.arange(ms.N_PIXELS) - (ms.N_PIXELS - 1) / 2.0) * PIXEL_PITCH_MM
    return (np.repeat(x[:, None], ms.N_PIXELS, axis=1),
            np.repeat(y[None, :], ms.N_TUBES, axis=0))


def synthetic_counts(dead_tube: int | None = DEAD_TUBE) -> np.ndarray:
    """A believable EQSANS image: 4-tube front/back packs, dead ends, beam stop."""
    rng = np.random.default_rng(0)
    counts = rng.normal(100.0, 3.0, size=(ms.N_TUBES, ms.N_PIXELS))

    # Front/back packs of four differ in level, as the real detector does.
    packs = (np.arange(ms.N_TUBES) // ms.TUBE_PACK) % 2
    counts[packs == 1] *= 0.65

    # Response falls away over the last few pixels at each end.
    ramp = np.ones(ms.N_PIXELS)
    ramp[:TRUE_BAND] = np.linspace(0.0, 0.35, TRUE_BAND)
    ramp[-TRUE_BAND:] = np.linspace(0.35, 0.0, TRUE_BAND)
    counts *= ramp[None, :]

    # Beam stop: a circle on the detector face, in millimetres.
    x_mm, y_mm = synthetic_positions()
    shadow = (x_mm ** 2 + y_mm ** 2) <= (TRUE_BEAM_R * PIXEL_PITCH_MM) ** 2
    counts[shadow] *= 0.02

    if dead_tube is not None:
        counts[dead_tube] *= 0.25
    return np.clip(counts, 0, None)


# --- counts ---------------------------------------------------------------

def test_reshape_accepts_a_detector_image():
    counts = ms.reshape_counts(synthetic_counts().reshape(-1))
    assert counts.shape == (ms.N_TUBES, ms.N_PIXELS)


def test_reshape_rejects_the_wrong_size():
    try:
        ms.reshape_counts(np.zeros(1000))
    except ValueError as exc:
        assert "49152" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_reshape_recovers_pixel_major_ordering():
    """If a future Mantid version hands back the transpose, say so and cope."""
    truth = synthetic_counts()
    recovered = ms.reshape_counts(truth.T.reshape(-1))
    assert recovered.shape == (ms.N_TUBES, ms.N_PIXELS)
    assert np.allclose(recovered, truth)


# --- shapes ---------------------------------------------------------------

def test_beam_stop_is_found_where_it_was_put():
    x_mm, y_mm = synthetic_positions()
    beam, why = ms.find_beam_stop(synthetic_counts(), x_mm, y_mm, scale=1.0, pad=0.0)
    assert beam is not None, why
    assert abs(beam.xc) < 4.0 and abs(beam.yc) < 4.0, (beam.xc, beam.yc)
    assert abs(beam.radius - TRUE_BEAM_R * PIXEL_PITCH_MM) < 12.0, beam.radius
    assert beam.core_contrast < 0.2, beam.core_contrast


def test_beam_scale_multiplies_and_pad_is_in_y_pixels():
    """`--beam-pad` keeps the machine-physics tool's units: pixels along a tube."""
    x_mm, y_mm = synthetic_positions()
    counts = synthetic_counts()
    base, _ = ms.find_beam_stop(counts, x_mm, y_mm, scale=1.0, pad=0.0)
    scaled, _ = ms.find_beam_stop(counts, x_mm, y_mm, scale=2.0, pad=0.0)
    padded, _ = ms.find_beam_stop(counts, x_mm, y_mm, scale=1.0, pad=7.0)
    assert abs(scaled.radius - 2 * base.radius) < 1e-6
    assert abs(padded.radius - (base.radius + 7 * PIXEL_PITCH_MM)) < 1e-6


def test_noise_alone_never_yields_a_beam_stop():
    """The reported bug: on a dim run (median 4 counts) ~9% of the detector dips
    below any global threshold, and a single-pass centroid returned a 70 mm
    circle nowhere near the beam."""
    rng = np.random.default_rng(1)
    counts = rng.poisson(4.0, size=(ms.N_TUBES, ms.N_PIXELS)).astype(float)
    x_mm, y_mm = synthetic_positions()
    beam, why = ms.find_beam_stop(counts, x_mm, y_mm)
    assert beam is None, (beam, why)
    assert why


def test_an_implausibly_large_detection_is_refused():
    counts = np.ones((ms.N_TUBES, ms.N_PIXELS)) * 100.0
    counts[40:150, 40:210] = 1.0          # a quarter of the detector "dark"
    x_mm, y_mm = synthetic_positions()
    beam, why = ms.find_beam_stop(counts, x_mm, y_mm)
    assert beam is None
    assert "darker" in why or "too far out" in why, why


def test_explicit_beam_center_and_radius_are_used_verbatim():
    x_mm, y_mm = synthetic_positions()
    plan = ms.build_plan(synthetic_counts(), x_mm, y_mm,
                         beam_center=(12.0, -8.0), beam_radius=31.0)
    assert plan.beam is not None
    assert (plan.beam.xc, plan.beam.yc, plan.beam.radius) == (12.0, -8.0, 31.0)
    assert plan.beam_note == "beam stop set explicitly"


def test_pixel_pitch_matches_the_real_detector():
    assert abs(ms.pixel_pitch_y_mm(synthetic_positions()[1]) - PIXEL_PITCH_MM) < 0.01


def test_masked_beam_region_is_a_disc_on_the_detector():
    """The point of masking in mm. Area is the robust measure -- a bounding box
    is quantised by the 5.49 mm tube pitch and 4.09 mm pixel pitch, which on a
    ~12-pixel disc is worth over 10% on its own."""
    x_mm, y_mm = synthetic_positions()
    counts = synthetic_counts()
    plan = ms.build_plan(counts, x_mm, y_mm)
    beam_only = ms.shapes_to_mask([plan.beam.as_shape()], x_mm, y_mm)

    area = beam_only.sum() * ms.pixel_area_mm2(x_mm, y_mm)
    expected = math.pi * plan.beam.radius ** 2
    assert abs(area - expected) / expected < 0.15, (area, expected)

    # And it is compact: every masked pixel lies within the stated radius.
    dist = np.hypot(x_mm[beam_only] - plan.beam.xc, y_mm[beam_only] - plan.beam.yc)
    assert dist.max() <= plan.beam.radius + 1e-6


def test_beam_mask_is_not_contiguous_in_tube_index():
    """Interleaving means a physical disc skips tube indices — the signature
    that the mask is spatial rather than index-space."""
    x_mm, y_mm = synthetic_positions()
    plan = ms.build_plan(synthetic_counts(), x_mm, y_mm)
    beam_only = ms.shapes_to_mask([plan.beam.as_shape()], x_mm, y_mm)
    touched = np.nonzero(beam_only.any(axis=1))[0]
    span = set(range(touched.min(), touched.max() + 1))
    assert span - set(touched.tolist()), "expected gaps from the pack interleave"


def test_beam_needs_positions():
    """Without real positions there is no honest circle, so none is drawn."""
    plan = ms.build_plan(synthetic_counts())
    assert plan.beam is None
    assert not ms.shapes_to_mask([{"type": "circle_mm", "xc": 0, "yc": 0, "r": 5}]).any()


def test_pixel_area_matches_the_real_detector():
    x_mm, y_mm = synthetic_positions()
    area = ms.pixel_area_mm2(x_mm, y_mm)
    assert abs(area - TUBE_PITCH_MM * PIXEL_PITCH_MM) < 0.5, area


def test_edge_bands_are_measured():
    bottom, top = ms.find_edge_bands(synthetic_counts())
    assert abs(bottom - TRUE_BAND) <= 3, bottom
    assert abs(top - TRUE_BAND) <= 3, top


def test_edge_bands_never_go_below_the_convention():
    """EQSANS has masked pixels 1-11 / 246-256 for years."""
    counts = synthetic_counts()
    counts[:, :3] = counts[:, 3:6]        # pretend the ends look healthy
    counts[:, -3:] = counts[:, -6:-3]
    plan = ms.build_plan(counts)
    assert plan.bottom >= ms.DEFAULT_MIN_BAND
    assert plan.top >= ms.DEFAULT_MIN_BAND


def test_dead_tube_is_flagged():
    plan = ms.build_plan(synthetic_counts(), *synthetic_positions())
    assert plan.tube_note == "", plan.tube_note
    assert DEAD_TUBE in plan.tubes, plan.tubes


def test_a_halo_across_the_centre_does_not_condemn_whole_tubes():
    """Run 186636 (9 m, 15 A): comparing tube MEANS flagged 29 tubes straight
    across the centre -- 22% of the detector -- because a broad bright halo
    around the beam stop lifted every tube crossing it. The median ignores a
    feature covering a minority of a tube's pixels."""
    x_mm, y_mm = synthetic_positions()
    counts = synthetic_counts(dead_tube=None)
    # a broad bright halo across the middle of every tube
    pixels = np.arange(ms.N_PIXELS)[None, :]
    halo = np.abs(pixels - ms.N_PIXELS // 2) < 25
    counts = counts + halo * 400.0

    by_mean = np.mean(counts[:, 11:245], axis=1)
    assert by_mean.std() > 0, "halo should move the means"
    tubes, _ = ms.find_deviant_tubes(counts, bottom=11, top=11)
    assert tubes == [], tubes


def test_tubes_are_not_judged_when_counts_are_too_low():
    """At ~1 count per pixel a dead tube and an unlucky one look identical."""
    rng = np.random.default_rng(3)
    counts = rng.poisson(1.0, size=(ms.N_TUBES, ms.N_PIXELS)).astype(float)
    tubes, note = ms.find_deviant_tubes(counts, bottom=11, top=11)
    assert tubes == []
    assert "too low to judge" in note, note


def test_gain_variation_is_not_masked():
    """10-20% tube-to-tube variation is normal and is what sensitivity corrects."""
    x_mm, y_mm = synthetic_positions()
    counts = synthetic_counts(dead_tube=None)
    counts[30] *= 0.85
    counts[31] *= 1.15
    tubes, _ = ms.find_deviant_tubes(counts, bottom=11, top=11)
    assert 30 not in tubes and 31 not in tubes, tubes


def test_healthy_detector_flags_nothing():
    plan = ms.build_plan(synthetic_counts(dead_tube=None), *synthetic_positions())
    assert plan.tubes == [], plan.tubes


def test_tube_grouping_is_by_packs_not_parity():
    """Comparing odd-to-odd leaves the two populations mixed and hides outliers.

    Measured on run 186104: MAD 2.7 by pack of four vs 19.9 by parity.
    """
    counts = synthetic_counts()
    totals = counts[:, TRUE_BAND:-TRUE_BAND].mean(axis=1)
    by_pack = (np.arange(ms.N_TUBES) // ms.TUBE_PACK) % 2
    spread_pack = np.mean([
        np.median(np.abs(totals[by_pack == g] - np.median(totals[by_pack == g])))
        for g in (0, 1)
    ])
    by_parity = np.arange(ms.N_TUBES) % 2
    spread_parity = np.mean([
        np.median(np.abs(totals[by_parity == g] - np.median(totals[by_parity == g])))
        for g in (0, 1)
    ])
    assert spread_pack < spread_parity / 3


def test_explicit_options_override_measurement():
    counts = synthetic_counts()
    plan = ms.build_plan(counts, bottom=4, top=6, tubes=[1, 2], use_beam=False)
    assert (plan.bottom, plan.top) == (4, 6)
    assert plan.tubes == [1, 2] and plan.tube_source == "manual"
    assert plan.beam is None


# --- mask assembly --------------------------------------------------------

def test_shapes_render_and_index_as_tube_major():
    shapes = [{"type": "rectangle", "x0": 3, "y0": 0, "x1": 3, "y1": 255}]
    mask = ms.shapes_to_mask(shapes)
    assert mask[3].all() and not mask[4].any()
    indices = ms.mask_to_indices(mask)
    # index = tube * N_PIXELS + pixel, verified against run 186104
    assert indices[0] == 3 * ms.N_PIXELS
    assert len(indices) == ms.N_PIXELS


def test_full_plan_masks_a_plausible_fraction():
    x_mm, y_mm = synthetic_positions()
    plan = ms.build_plan(synthetic_counts(), x_mm, y_mm)
    mask = ms.shapes_to_mask(plan.shapes, x_mm, y_mm)
    fraction = mask.sum() / mask.size
    assert 0.05 < fraction < 0.15, fraction


def test_disc_masks_where_asked_and_is_round():
    """--disc is in millimetres: tube index is not a spatial coordinate, so a
    disc specified in index space would not be round on the detector."""
    x_mm, y_mm = synthetic_positions()
    plan = ms.build_plan(synthetic_counts(), x_mm, y_mm, use_beam=False,
                         use_tubes=False, bottom=0, top=0,
                         discs=[(100.0, -50.0, 20.0)])
    mask = ms.shapes_to_mask(plan.shapes, x_mm, y_mm)
    assert abs(float(x_mm[mask].mean()) - 100.0) < 3.0
    assert abs(float(y_mm[mask].mean()) + 50.0) < 3.0
    area = mask.sum() * ms.pixel_area_mm2(x_mm, y_mm)
    assert abs(area - math.pi * 400) / (math.pi * 400) < 0.1, area


def test_several_discs_compose():
    x_mm, y_mm = synthetic_positions()
    plan = ms.build_plan(synthetic_counts(), x_mm, y_mm, use_beam=False,
                         use_tubes=False, bottom=0, top=0,
                         discs=[(-300.0, 300.0, 40.0), (250.0, -250.0, 25.0)])
    assert len(plan.discs) == 2
    mask = ms.shapes_to_mask(plan.shapes, x_mm, y_mm)
    for xc, yc, radius in plan.discs:
        one = ms.shapes_to_mask([{"type": "circle_mm", "xc": xc, "yc": yc, "r": radius}],
                                x_mm, y_mm)
        assert one.any() and (one & mask).sum() == one.sum()


def test_disc_off_the_detector_is_detected():
    x_mm, y_mm = synthetic_positions()
    assert ms.disc_is_on_detector(100.0, -50.0, 20.0, x_mm, y_mm)
    assert not ms.disc_is_on_detector(900.0, 900.0, 20.0, x_mm, y_mm)


def test_disc_option_parsing():
    from eqsanscli.commands.mask import _parse_args

    opts, err = _parse_args(["--disc", "500,500,20", "--disc", "0,0,25"])
    assert not err
    assert opts["discs"] == [(500.0, 500.0, 20.0), (0.0, 0.0, 25.0)]
    assert _parse_args(["--disc", "1,2"])[1]
    assert _parse_args(["--disc", "1,2,-3"])[1]


def test_preview_axes_run_left_to_right():
    """Tubes are ordered by ascending x so the plotted mm axis reads normally."""
    x_mm, _ = synthetic_positions()
    order = ms.physical_tube_order(x_mm)
    ordered = x_mm[order][:, 0]
    assert np.all(np.diff(ordered) > 0)


def _counts_with_gravity_streak():
    """A stop blocking the middle of a vertically smeared direct beam.

    Gravity drop goes as wavelength squared, so across the band the beam lands at
    a range of heights; a stop sized for the middle lets the ends through. This is
    run 186636 in miniature.
    """
    counts = synthetic_counts(dead_tube=None)
    x_mm, y_mm = synthetic_positions()
    column = np.abs(x_mm) < 30.0
    counts[column & (y_mm > 25) & (y_mm < 80)] = 400.0     # upper lobe
    counts[column & (y_mm < -25) & (y_mm > -80)] = 300.0    # lower lobe
    return counts


def test_gravity_dropped_beam_extends_the_mask_into_a_capsule():
    x_mm, y_mm = synthetic_positions()
    plan = ms.build_plan(_counts_with_gravity_streak(), x_mm, y_mm,
                         use_tubes=False, bottom=0, top=0)
    beam = plan.beam
    assert beam is not None and beam.is_streak, beam
    assert beam.leaks >= 2, beam.leaks
    assert beam.y_low < -60 and beam.y_high > 60, (beam.y_low, beam.y_high)
    assert plan.beam.as_shape()["type"] == "capsule_mm"


def test_the_capsule_covers_every_bright_leak_pixel():
    """A single unmasked direct-beam pixel ruins the low-Q data it lands in."""
    x_mm, y_mm = synthetic_positions()
    counts = _counts_with_gravity_streak()
    plan = ms.build_plan(counts, x_mm, y_mm, use_tubes=False, bottom=0, top=0)
    mask = ms.shapes_to_mask([plan.beam.as_shape()], x_mm, y_mm)
    bright = counts > 250.0
    assert bright.any()
    assert (bright & ~mask).sum() == 0, int((bright & ~mask).sum())


def test_no_leak_keeps_the_plain_disc():
    x_mm, y_mm = synthetic_positions()
    plan = ms.build_plan(_counts_with_gravity_streak(), x_mm, y_mm,
                         use_tubes=False, bottom=0, top=0, include_leaks=False)
    assert plan.beam is not None and not plan.beam.is_streak
    assert plan.beam.as_shape()["type"] == "circle_mm"


def test_a_clean_stop_is_not_turned_into_a_capsule():
    """Short wavelength: no leakage, so the mask must stay a circle."""
    x_mm, y_mm = synthetic_positions()
    plan = ms.build_plan(synthetic_counts(dead_tube=None), x_mm, y_mm,
                         use_tubes=False, bottom=0, top=0)
    assert plan.beam is not None and not plan.beam.is_streak
    assert plan.beam.leaks == 0


def test_capsule_shape_renders_as_a_stadium():
    x_mm, y_mm = synthetic_positions()
    shape = {"type": "capsule_mm", "xc": 0.0, "y0": -100.0, "y1": 100.0, "r": 20.0}
    mask = ms.shapes_to_mask([shape], x_mm, y_mm)
    assert mask[np.abs(x_mm) < 5][np.abs(y_mm[np.abs(x_mm) < 5]) < 90].all()
    # rounded ends: nothing beyond the segment plus the radius
    assert y_mm[mask].max() <= 100.0 + 20.0 + 1e-6
    assert y_mm[mask].min() >= -100.0 - 20.0 - 1e-6


def test_no_leak_option_parsing():
    from eqsanscli.commands.mask import _parse_args

    assert _parse_args(["--no-leak"])[0]["include_leaks"] is False
    assert _parse_args([])[0]["include_leaks"] is True


def test_unknown_shape_is_ignored_not_fatal():
    assert not ms.shapes_to_mask([{"type": "triangle"}]).any()


# --- naming and discoverability -------------------------------------------

def test_config_token_uses_the_o_convention():
    assert ms.config_token(4.0, 10.0, 60) == "4m10a"
    assert ms.config_token(4.0, 2.5, 60) == "4m2o5a"
    assert ms.config_token(2.5, 2.5, 60) == "2o5m2o5a"
    assert ms.config_token(1.3, 2.5, 60) == "1o3m2o5a"
    assert ms.config_token(4.0, 2.5, 30) == "4m2o5a30hz"


def test_filenames_are_read_back_by_the_mask_resolver():
    """The naming is what makes a mask discoverable — close that loop."""
    from eqsanscli.services.instrument_files import _parse_mask_tokens

    for distance, wavelength, frequency in ((4.0, 10.0, 60), (4.0, 2.5, 60),
                                            (2.5, 2.5, 60), (1.3, 2.5, 60),
                                            (4.0, 2.5, 30)):
        name = ms.mask_filename(distance, wavelength, frequency, 186104)
        got_d, got_w, frame_skip = _parse_mask_tokens(name)
        assert got_d == distance, (name, got_d)
        assert got_w == wavelength, (name, got_w)
        assert frame_skip == (frequency == 30), name


def test_filename_starts_with_mask_so_the_resolver_globs_it():
    assert ms.mask_filename(4.0, 2.5, 60, 1).startswith("mask")
    assert ms.mask_filename(4.0, 2.5, 60, 1).endswith(".nxs")


def test_resolve_run_file_reports_where_it_looked():
    path, searched = ms.resolve_run_file("999999", 12345)
    assert path is None
    assert any("IPTS-12345" in s for s in searched)


# --- command plumbing -----------------------------------------------------

def test_option_parsing():
    from eqsanscli.commands.mask import _parse_args

    opts, err = _parse_args(["--ipts", "37618", "--beam-scale", "1.4",
                             "--tubes", "1,2,3", "--no-beam", "--dry-run"])
    assert not err
    assert opts["ipts"] == "37618" and opts["beam_scale"] == 1.4
    assert opts["tubes"] == [1, 2, 3] and opts["use_beam"] is False
    assert opts["dry_run"] is True


def test_option_parsing_rejects_bad_input():
    from eqsanscli.commands.mask import _parse_args

    assert _parse_args(["--beam-scale", "wide"])[1]
    assert _parse_args(["--ipts"])[1]
    assert _parse_args(["--nonsense"])[1]


def test_mask_command_is_registered():
    from eqsanscli.commands.registry import register_all
    from eqsanscli.commands.router import CommandRouter

    router = CommandRouter()
    register_all(router)
    assert "mask" in router.commands


if __name__ == "__main__":
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001 - standalone runner
            print(f"  FAIL  {name}: {exc}")
            failures.append(name)
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed"
          + (f" — FAILED: {', '.join(failures)}" if failures else ""))
    sys.exit(1 if failures else 0)
