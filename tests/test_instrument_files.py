"""Run-aware instrument-file resolution.

Two groups of checks: a synthetic folder tree (always runs, exercises the
policy) and the live machine-physics share (skipped when not mounted, pins the
behaviour to real data).

    python tests/test_instrument_files.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.services import instrument_files as ifiles
from eqsanscli.services.instrument_files import (
    DEFAULT_MP_ROOT, MANAGED_PARAMS, PARAM_DARK, PARAM_DETOFFSET, PARAM_FLUX,
    PARAM_SAMPLEOFFSET, PARAM_SCALECOMP, PARAM_SENSITIVITY,
    flood_distance_for, resolve_for_run, scan_cycles, select_cycle, verify_paths,
)

LIVE = os.path.isdir(DEFAULT_MP_ROOT)


# --------------------------------------------------------------------------
# Synthetic tree
# --------------------------------------------------------------------------

def _touch(path: str, size: int = 16) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(b"x" * size)


def _build_tree(root: str) -> None:
    """Two full cycles plus one older, mirroring real naming.

    2030A: anchor 300000, all three floods, flux, AgBe
    2030B: anchor 310000, only 4 m flood, no flux, no AgBe
    2029B: anchor 290000, 2.5 m flood only, flux
    """
    a = os.path.join(root, "2030A_mp")
    _touch(os.path.join(a, "EQSANS_300000.nxs.h5"), 900)
    _touch(os.path.join(a, "Sensitivity_patched_thinPMMA_4m_300002.nxs"))
    _touch(os.path.join(a, "Sensitivity_patched_thinPMMA_2o5m_300003.nxs"))
    _touch(os.path.join(a, "Sensitivity_patched_thinPMMA_1o3m_300004.nxs"))
    _touch(os.path.join(a, "Sensitivity_patched_5mmPMMA_4m_300009.nxs"))  # higher run, not preferred
    _touch(os.path.join(a, "bl6_flux_2030A_jan_rebinned.txt"))
    ck = os.path.join(a, "agbe_calibration", "agbe_40000", "checkpoint.json")
    os.makedirs(os.path.dirname(ck), exist_ok=True)
    with open(ck, "w") as fh:
        fh.write('{"completed_steps":["a","b","c"],"results":{"scale_y":1.05,'
                 '"scale_all":1.004,"detoffset":66.5,"scalecomp":[1.004,1.058,1]}}')
    with open(os.path.join(os.path.dirname(ck), "calibration_report.txt"), "w") as fh:
        fh.write("scale_y: 1.05\ndetoffset: 66.5\nsamoffset: 285.0\n"
                 "scalecomp = [1.004, 1.058, 1]\n")

    b = os.path.join(root, "2030B_mp")
    _touch(os.path.join(b, "EQSANS_310000.nxs.h5"), 900)
    _touch(os.path.join(b, "Sensitivity_patched_thinPMMA_4m_310002.nxs"))

    c = os.path.join(root, "2029B_mp")
    _touch(os.path.join(c, "EQSANS_290000.nxs.h5"), 900)
    _touch(os.path.join(c, "Sensitivity_patched_thinPMMA_2o5m_290002.nxs"))
    _touch(os.path.join(c, "bl6_flux_2029B_aug_rebinned.txt"))


class _Tree:
    def __enter__(self):
        self._tmp = tempfile.TemporaryDirectory()
        _build_tree(self._tmp.name)
        os.environ[ifiles.MP_ROOT_ENV] = self._tmp.name
        ifiles.clear_cache()
        return self._tmp.name

    def __exit__(self, *exc):
        os.environ.pop(ifiles.MP_ROOT_ENV, None)
        ifiles.clear_cache()
        self._tmp.cleanup()
        return False


def test_synthetic_scan_finds_cycles_and_anchors():
    with _Tree():
        cycles = scan_cycles()
        assert [c.cycle_id for c in cycles] == ["2030B", "2030A", "2029B"]
        assert [c.anchor_run for c in cycles] == [310000, 300000, 290000]


def test_cycle_selection_is_run_based():
    with _Tree():
        cycles = scan_cycles()
        assert select_cycle(305000, cycles).cycle_id == "2030A"
        assert select_cycle(310000, cycles).cycle_id == "2030B"
        assert select_cycle(299999, cycles).cycle_id == "2029B"
        assert select_cycle(1, cycles) is None


def test_resolution_is_cycle_coherent():
    with _Tree():
        r = resolve_for_run(305000, 4.0)
        assert r.cycle_id == "2030A"
        assert r.cycles_used() == ["2030A"]
        assert os.path.basename(str(r.values[PARAM_SENSITIVITY])) == \
            "Sensitivity_patched_thinPMMA_4m_300002.nxs"
        assert r.values[PARAM_DETOFFSET] == 66.5
        assert r.values[PARAM_SCALECOMP] == [1.004, 1.058, 1.0]
        assert r.values[PARAM_SAMPLEOFFSET] == 285.0


def test_preferred_variant_beats_higher_run():
    with _Tree():
        r = resolve_for_run(305000, 4.0)
        # 5mmPMMA_4m_300009 has the higher run but thinPMMA wins.
        assert "thinPMMA" in str(r.values[PARAM_SENSITIVITY])


def test_missing_distance_falls_back_to_earlier_cycle():
    with _Tree():
        r = resolve_for_run(315000, 2.5)   # 2030B has only the 4 m flood
        assert r.cycle_id == "2030B"
        assert r.params[PARAM_DARK].cycle_id == "2030B"
        sens = r.params[PARAM_SENSITIVITY]
        assert sens.cycle_id == "2030A"
        assert "2030A" in sens.note


def test_flux_falls_back_one_cycle_then_stops():
    with _Tree():
        # 2030B has no flux; 2030A (one back) does.
        r = resolve_for_run(315000, 4.0)
        assert r.params[PARAM_FLUX].cycle_id == "2030A"

        # From 2030A, the only earlier flux is 2029B (one back) — allowed.
        r2 = resolve_for_run(305000, 4.0)
        assert r2.params[PARAM_FLUX].cycle_id == "2030A"


def test_flux_not_taken_from_two_cycles_back():
    with _Tree() as root:
        os.remove(os.path.join(root, "2030A_mp", "bl6_flux_2030A_jan_rebinned.txt"))
        ifiles.clear_cache()
        r = resolve_for_run(315000, 4.0)   # 2030B -> 2030A (none) -> stop
        assert PARAM_FLUX not in r.params
        assert any("beam flux" in m for m in r.missing)


def test_no_agbe_leaves_calibration_untouched():
    with _Tree():
        r = resolve_for_run(295000, 2.5)   # 2029B, no AgBe anywhere at/below
        for param in (PARAM_DETOFFSET, PARAM_SCALECOMP, PARAM_SAMPLEOFFSET):
            assert param not in r.params
        assert any("AgBe" in m for m in r.missing)


def test_run_predating_all_cycles_resolves_nothing():
    with _Tree():
        r = resolve_for_run(1000, 4.0)
        assert r.params == {}
        assert any("predates" in m for m in r.missing)


def test_pin_cycle_overrides_run_number():
    with _Tree():
        r = resolve_for_run(315000, 4.0, pin_cycle="2030A")
        assert r.cycle_id == "2030A"
        assert "300002" in str(r.values[PARAM_SENSITIVITY])
        r_bad = resolve_for_run(315000, 4.0, pin_cycle="1999A")
        assert r_bad.params == {}
        assert any("not found" in m for m in r_bad.missing)


def test_note_when_chosen_file_is_newer_than_run():
    with _Tree():
        # Data run between the dark (300000) and the floods (300002+).
        r = resolve_for_run(300001, 4.0)
        assert r.cycle_id == "2030A"
        assert any("> data run" in n for n in r.notes)


def test_missing_root_is_reported_not_raised():
    os.environ[ifiles.MP_ROOT_ENV] = "/nonexistent/mp/root"
    ifiles.clear_cache()
    try:
        r = resolve_for_run(305000, 4.0)
        assert r.params == {}
        assert any("No cycle folders" in m for m in r.missing)
    finally:
        os.environ.pop(ifiles.MP_ROOT_ENV, None)
        ifiles.clear_cache()


def test_verify_paths_flags_missing_and_empty():
    with tempfile.TemporaryDirectory() as d:
        empty = os.path.join(d, "empty.nxs")
        open(empty, "w").close()
        problems = verify_paths({
            PARAM_SENSITIVITY: os.path.join(d, "gone.nxs"),
            PARAM_DARK: empty,
        })
        assert any("missing file" in p for p in problems)
        assert any("empty file" in p for p in problems)


# --------------------------------------------------------------------------
# Distance mapping (no filesystem)
# --------------------------------------------------------------------------

def test_flood_distance_mapping():
    tags = [1.3, 2.5, 4.0]
    assert flood_distance_for(1.3, tags) == 1.3
    assert flood_distance_for(1.0, tags) == 1.3     # clamped below
    assert flood_distance_for(2.5, tags) == 2.5
    assert flood_distance_for(2.0, tags) == 2.5     # tie -> larger
    assert flood_distance_for(4.0, tags) == 4.0
    assert flood_distance_for(5.0, tags) == 4.0     # clamped above
    assert flood_distance_for(8.0, tags) == 4.0     # the user's 8 m case
    assert flood_distance_for(4.0, []) is None


# --------------------------------------------------------------------------
# Live share
# --------------------------------------------------------------------------

def test_live_anchor_runs_are_monotonic_with_cycle():
    if not LIVE:
        print("      (skipped: machine-physics share not mounted)")
        return
    cycles = sorted(scan_cycles(DEFAULT_MP_ROOT), key=lambda c: c.cycle_id)
    runs = [c.anchor_run for c in cycles]
    assert runs == sorted(runs), [
        (c.cycle_id, c.anchor_run) for c in cycles
    ]


def test_live_current_cycle_resolves_to_2026b():
    if not LIVE:
        print("      (skipped: machine-physics share not mounted)")
        return
    r = resolve_for_run(186500, 4.0, root=DEFAULT_MP_ROOT)
    assert r.cycle_id == "2026B"
    assert r.values[PARAM_SENSITIVITY].endswith(
        "2026B_mp/Sensitivity_patched_thinPMMA_4m_186200.nxs")
    assert r.values[PARAM_DARK].endswith("2026B_mp/EQSANS_186198.nxs.h5")
    assert r.values[PARAM_FLUX].endswith("2026B_mp/bl6_flux_2026B_aug_rebinned.txt")
    assert round(r.values[PARAM_DETOFFSET], 3) == 66.763
    assert [round(v, 6) for v in r.values[PARAM_SCALECOMP]] == [1.004251, 1.057915, 1.0]
    assert r.values[PARAM_SAMPLEOFFSET] == 285.0
    assert not r.missing


def test_live_long_distance_uses_4m_flood():
    if not LIVE:
        print("      (skipped: machine-physics share not mounted)")
        return
    r = resolve_for_run(186500, 8.0, root=DEFAULT_MP_ROOT)
    assert "_4m_186200" in r.values[PARAM_SENSITIVITY]
    assert "4 m flood" in r.params[PARAM_SENSITIVITY].note


def test_live_2025b_prefers_thinpmma():
    if not LIVE:
        print("      (skipped: machine-physics share not mounted)")
        return
    # 2025B holds thinPMMA (167517) and 5mmPMMA (167518) at 4 m.
    r = resolve_for_run(172804, 4.0, root=DEFAULT_MP_ROOT)
    assert r.cycle_id == "2025B"
    assert "thinPMMA_4m_167517" in r.values[PARAM_SENSITIVITY]


def test_live_pre_2026a_run_gets_no_agbe():
    if not LIVE:
        print("      (skipped: machine-physics share not mounted)")
        return
    r = resolve_for_run(172804, 4.0, root=DEFAULT_MP_ROOT)
    for param in (PARAM_DETOFFSET, PARAM_SCALECOMP, PARAM_SAMPLEOFFSET):
        assert param not in r.params
    assert any("AgBe" in m for m in r.missing)


def test_live_old_run_does_not_reach_back_to_2013_flux():
    if not LIVE:
        print("      (skipped: machine-physics share not mounted)")
        return
    r = resolve_for_run(150000, 4.0, root=DEFAULT_MP_ROOT)
    assert r.cycle_id == "2024B"
    assert PARAM_FLUX not in r.params      # 2013B's stray flux must not be used
    assert "2024B_mp" in r.values[PARAM_SENSITIVITY]


def test_live_boundary_run_stays_within_one_cycle():
    if not LIVE:
        print("      (skipped: machine-physics share not mounted)")
        return
    # Dark 186198 <= 186199 < floods 186200-186202.
    r = resolve_for_run(186199, 4.0, root=DEFAULT_MP_ROOT)
    assert r.cycles_used() == ["2026B"]
    assert any("> data run 186199" in n for n in r.notes)


def test_live_resolved_files_exist():
    if not LIVE:
        print("      (skipped: machine-physics share not mounted)")
        return
    r = resolve_for_run(186500, 4.0, root=DEFAULT_MP_ROOT)
    assert verify_paths(r.values) == []


# --------------------------------------------------------------------------
# Applying to a session (synthetic tree, no live share needed)
# --------------------------------------------------------------------------

def _session(runs=((305000, 4.0),)):
    from eqsanscli.models.session_state import SessionState
    from eqsanscli.models.working_table import WorkingTableRow

    state = SessionState()
    state.ipts = 1
    for i, (run, distance) in enumerate(runs):
        state.current_table.add_row(WorkingTableRow(
            index=0, scattering_run=str(run), sample_name=f"S{i}",
            detector_distance=distance, wavelength=10.0, frequency=60,
        ))
    return state


def test_sync_writes_every_managed_param_it_can_resolve():
    with _Tree():
        state = _session()
        outcomes, warnings = ifiles.sync_state_configs(state)
        assert len(outcomes) == 1
        # The synthetic tree has no mask anywhere, so mask is expected to be
        # absent; everything else must be written.
        expected = set(MANAGED_PARAMS) - {ifiles.PARAM_MASK}
        assert set(outcomes[0].written) == expected
        assert warnings == []


def test_sync_keeps_user_set_value_but_force_overrides():
    with _Tree():
        state = _session()
        cfg = state.current_table.configurations[0]
        state.configurations[cfg] = {PARAM_SENSITIVITY: "/my/own/flood.nxs"}

        outcomes, _ = ifiles.sync_state_configs(state)
        assert PARAM_SENSITIVITY in outcomes[0].kept_user
        assert state.configurations[cfg][PARAM_SENSITIVITY] == "/my/own/flood.nxs"

        outcomes, _ = ifiles.sync_state_configs(state, force=True)
        assert PARAM_SENSITIVITY in outcomes[0].written
        assert "300002" in state.configurations[cfg][PARAM_SENSITIVITY]


def test_resync_updates_its_own_earlier_value():
    """A new cycle's files replace the previous resolve without --force."""
    with _Tree():
        state = _session(runs=((305000, 4.0),))
        ifiles.sync_state_configs(state)
        cfg = state.current_table.configurations[0]
        assert "300002" in state.configurations[cfg][PARAM_SENSITIVITY]

        # Same config, but now pinned to the newer cycle: resolver-owned value
        # is replaceable, so it updates.
        state.instrument_cycle_pin = "2030B"
        outcomes, _ = ifiles.sync_state_configs(state)
        assert "310002" in state.configurations[cfg][PARAM_SENSITIVITY]
        assert PARAM_SENSITIVITY in outcomes[0].written


def test_straddle_warning_when_runs_span_cycles():
    with _Tree():
        state = _session(runs=((305000, 4.0), (315000, 4.0)))
        # Both rows are 4 m / 10 A, so they share one config.
        assert len(state.current_table.configurations) == 1
        _, warnings = ifiles.sync_state_configs(state)
        assert any("straddle" in w for w in warnings)


def test_config_targets_key_on_lowest_run():
    with _Tree():
        state = _session(runs=((315000, 4.0), (305000, 4.0)))
        target = ifiles.config_targets(state)[0]
        assert target.run == 305000
        assert target.max_run == 315000


def test_runs_in_handles_multi_run_strings():
    from eqsanscli.models.working_table import WorkingTableRow

    row = WorkingTableRow(index=1, scattering_run="172760, 172761", sample_name="X")
    assert ifiles.runs_in(row) == [172760, 172761]
    assert ifiles.runs_in(WorkingTableRow(index=1, scattering_run="", sample_name="X")) == []


def test_matchruns_resolves_and_respects_off_switch():
    import asyncio

    import pandas as pd

    from eqsanscli.commands.matching import handle_matchruns

    def run(coro):
        return asyncio.new_event_loop().run_until_complete(coro)

    catalog = pd.DataFrame([{
        "run_number": 305000, "title": "S-Samp 4m 10a", "detector_distance": 4.0,
        "wavelength": 10.0, "frequency": 60, "run_class": "scattering",
    }])

    with _Tree():
        state = _session(runs=())
        state.catalog = catalog
        result = run(handle_matchruns([], state))
        assert result.success
        assert "Instrument files" in result.message
        cfg = state.current_table.configurations[0]
        assert "300002" in state.configurations[cfg][PARAM_SENSITIVITY]

    with _Tree():
        state = _session(runs=())
        state.catalog = catalog
        state.auto_instrument_files = False
        result = run(handle_matchruns([], state))
        cfg = state.current_table.configurations[0]
        # The JSON preset still supplies its own (cycle-specific, eventually
        # stale) path — that is the deliberate offline fallback. What must NOT
        # happen is a machine-physics resolution.
        assert "300002" not in str(state.configurations.get(cfg, {}).get(PARAM_SENSITIVITY))
        assert not state.instrument_provenance
        assert "resolution is off" in result.message


def test_instrument_show_preview_matches_apply():
    import asyncio

    from eqsanscli.commands.instrument import handle_instrument

    def run(coro):
        return asyncio.new_event_loop().run_until_complete(coro)

    with _Tree():
        state = _session()
        cfg = state.current_table.configurations[0]
        state.configurations[cfg] = {PARAM_SENSITIVITY: "/my/own/flood.nxs"}

        shown = run(handle_instrument(["show"], state)).message
        assert "kept" in shown            # the user's value is flagged as kept
        applied = run(handle_instrument(["apply"], state)).message
        assert "kept your values" in applied
        assert state.configurations[cfg][PARAM_SENSITIVITY] == "/my/own/flood.nxs"


def test_session_round_trip_keeps_provenance_and_switches():
    import tempfile as _tf

    from eqsanscli.models.session_state import SessionState

    with _Tree():
        state = _session()
        ifiles.sync_state_configs(state)
        state.instrument_cycle_pin = "2030A"
        state.auto_instrument_files = False
        with _tf.TemporaryDirectory() as d:
            path = os.path.join(d, "s.json")
            state.save(path)
            loaded = SessionState.load(path)
    assert loaded.instrument_cycle_pin == "2030A"
    assert loaded.auto_instrument_files is False
    cfg = next(iter(loaded.instrument_provenance))
    assert set(loaded.instrument_provenance[cfg]) == set(MANAGED_PARAMS) - {ifiles.PARAM_MASK}


# --------------------------------------------------------------------------
# Masks
# --------------------------------------------------------------------------

def test_mask_token_parsing_on_real_names():
    from eqsanscli.services.instrument_files import _parse_mask_tokens

    assert _parse_mask_tokens("mask_4m.nxs") == (4.0, None, False)
    assert _parse_mask_tokens("mask_8m3mm.nxs") == (8.0, None, False)      # not 3 m
    assert _parse_mask_tokens("mask_2o5m.nxs") == (2.5, None, False)
    assert _parse_mask_tokens("maskWS4m10A.nxs") == (4.0, 10.0, False)
    assert _parse_mask_tokens("maskWS4m2p5A_FS.nxs") == (4.0, 2.5, True)   # 2p5 = 2.5
    assert _parse_mask_tokens("EQSANS_186104_mask.nxs") == (None, None, False)


def test_mask_pick_matches_distance_and_wavelength():
    from eqsanscli.services.instrument_files import MaskFile, pick_mask

    cands = [
        MaskFile("/x/maskWS4m10A.nxs", 4.0, 10.0, False, "cwd"),
        MaskFile("/x/maskWS4m2p5A_FS.nxs", 4.0, 2.5, True, "cwd"),
    ]
    assert pick_mask("4m10a", cands).name == "maskWS4m10A.nxs"
    assert pick_mask("4m2.5a", cands).name == "maskWS4m2p5A_FS.nxs"
    # A different distance must not borrow a 4 m mask.
    assert pick_mask("8m10a", cands) is None


def test_mask_pick_prefers_specific_over_generic():
    from eqsanscli.services.instrument_files import MaskFile, pick_mask

    cands = [
        MaskFile("/x/mask_4m.nxs", 4.0, None, False, "cwd"),
        MaskFile("/x/mask.nxs", None, None, False, "cwd"),
    ]
    assert pick_mask("4m10a", cands).name == "mask_4m.nxs"
    # A token-less mask still serves a config nothing else matches.
    assert pick_mask("1.3m2.5a", cands).name == "mask.nxs"


def test_mask_prefers_working_folder_over_ipts_shared(tmp=None):
    import tempfile

    from eqsanscli.services.instrument_files import resolve_mask

    with _Tree():
        cycles = scan_cycles()
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "mask_4m.nxs"), "w") as fh:
                fh.write("x")
            mask, searched = resolve_mask("4m10a", cycles, cwd=d, ipts=38773)
    assert mask is not None
    assert mask.origin == "cwd"
    assert mask.name == "mask_4m.nxs"
    assert searched and searched[0] == d


def test_mask_falls_back_to_cycle_default():
    import tempfile

    from eqsanscli.services.instrument_files import resolve_mask

    with _Tree() as root:
        # Give the newest cycle a masks/ folder with a token-less default.
        masks_dir = os.path.join(root, "2030B_mp", "masks")
        os.makedirs(masks_dir, exist_ok=True)
        with open(os.path.join(masks_dir, "EQSANS_310004_mask.nxs"), "w") as fh:
            fh.write("x")
        ifiles.clear_cache()
        cycles = scan_cycles()
        newest = [c for c in cycles if c.cycle_id == "2030B"]
        with tempfile.TemporaryDirectory() as empty:
            mask, searched = resolve_mask("4m10a", newest, cwd=empty, ipts=None)
    assert mask is not None
    assert mask.name == "EQSANS_310004_mask.nxs"
    assert "masks/" in mask.origin


def test_mask_missing_reports_every_location_searched():
    import tempfile

    from eqsanscli.services.instrument_files import (
        MASK_MISSING_PREFIX, PARAM_MASK, resolve_for_run,
    )

    with _Tree():
        cycles = scan_cycles()
        with tempfile.TemporaryDirectory() as empty:
            res = resolve_for_run(
                305000, 4.0, cycles=cycles, config_id="4m10a", cwd=empty, ipts=None,
            )
    assert PARAM_MASK not in res.params
    problem = next(m for m in res.missing if m.startswith(MASK_MISSING_PREFIX))
    assert "Looked in:" in problem
    assert "/set config 4m10a maskfilename" in problem


def test_mask_is_a_managed_param_and_verified():
    from eqsanscli.services.instrument_files import MANAGED_PARAMS, PARAM_MASK, verify_paths

    assert PARAM_MASK in MANAGED_PARAMS
    problems = verify_paths({PARAM_MASK: "/definitely/not/here_mask.nxs"})
    assert any("mask" in p for p in problems)


def test_presets_carry_no_foreign_ipts_paths():
    """A mask from another IPTS's shared folder is often unreadable to others."""
    import glob
    import json

    for path in glob.glob(str(Path(__file__).resolve().parent.parent
                              / "preset_configs" / "conf_*.json")):
        text = json.dumps(json.load(open(path)))
        assert "/SNS/EQSANS/IPTS-" not in text, path


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
