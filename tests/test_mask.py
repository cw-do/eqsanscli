"""Mask geometry — pure numpy, no Mantid needed.

The Mantid-facing halves (reading a run's counts, writing the NeXus) are
exercised by actually running `/mask create` against a real run; what is tested
here is the part that decides *what* to mask, on a synthetic detector whose
answers are known.

    python tests/test_mask.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from eqsanscli.services import mask_service as ms

TRUE_BEAM_X, TRUE_BEAM_Y, TRUE_BEAM_R = 91.0, 131.0, 6.0
TRUE_BAND = 11
DEAD_TUBE = 57


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

    # Beam stop: a physical circle, so an ellipse in index space.
    xs = np.arange(ms.N_TUBES)[:, None]
    ys = np.arange(ms.N_PIXELS)[None, :]
    aspect = ms.N_PIXELS / ms.N_TUBES
    shadow = (((xs - TRUE_BEAM_X) / TRUE_BEAM_R) ** 2
              + ((ys - TRUE_BEAM_Y) / (TRUE_BEAM_R * aspect)) ** 2) <= 1.0
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
    beam = ms.find_beam_stop(synthetic_counts())
    assert beam is not None
    assert abs(beam.xc - TRUE_BEAM_X) < 1.5, beam.xc
    assert abs(beam.yc - TRUE_BEAM_Y) < 1.5, beam.yc
    # Radii keep the physical circle's aspect ratio.
    assert abs(beam.ry / beam.rx - ms.N_PIXELS / ms.N_TUBES) < 0.35


def test_beam_scale_and_pad_enlarge_it():
    small = ms.find_beam_stop(synthetic_counts(), scale=1.0, pad=0.0)
    big = ms.find_beam_stop(synthetic_counts(), scale=2.0, pad=3.0)
    assert big.rx > small.rx and big.ry > small.ry + 2


def test_beam_stays_circular_under_both_knobs():
    """Padding only ry would stretch the circle vertically (13% off at pad 1)."""
    counts = synthetic_counts()
    aspect = ms.N_PIXELS / ms.N_TUBES
    for scale, pad in ((1.0, 0.0), (1.2, 1.0), (1.2, 6.0), (1.0, 6.0), (2.0, 2.0)):
        beam = ms.find_beam_stop(counts, scale=scale, pad=pad)
        assert abs(beam.ry / beam.rx - aspect) < 1e-6, (scale, pad, beam)


def test_pad_is_quoted_in_pixels():
    """`--beam-pad 4` adds 4 pixels on y, and the matching arc on x."""
    counts = synthetic_counts()
    base = ms.find_beam_stop(counts, scale=1.0, pad=0.0)
    padded = ms.find_beam_stop(counts, scale=1.0, pad=4.0)
    assert abs((padded.ry - base.ry) - 4.0) < 1e-6
    assert abs((padded.rx - base.rx) - 4.0 / (ms.N_PIXELS / ms.N_TUBES)) < 1e-6


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
    plan = ms.build_plan(synthetic_counts())
    assert DEAD_TUBE in plan.tubes, plan.tubes


def test_healthy_detector_flags_nothing():
    plan = ms.build_plan(synthetic_counts(dead_tube=None))
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
    plan = ms.build_plan(synthetic_counts())
    mask = ms.shapes_to_mask(plan.shapes)
    fraction = mask.sum() / mask.size
    assert 0.05 < fraction < 0.15, fraction


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
