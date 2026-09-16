"""/retitle — correcting a run title so /matchruns can pair it.

From IPTS-36552: the transmissions were labelled by sample-changer slot
(`T-s1 4m 10A` … `T-s11 4m 10A`) while the scattering runs carried real sample
names (`S-L62_0 4m 10A` …). /matchruns pairs on the sample name parsed from the
title, so not one of the 261 scattering runs found its transmission, and no
amount of /set fixed the *next* /matchruns. Correcting the title does.

Two properties matter enough to pin down here:
  1. the swap is whole-word — `s1` must not rewrite `s10`/`s11`, which would
     have mislabelled two samples in that very experiment;
  2. corrections survive a catalog reload, since ONCat keeps serving the
     original titles.

    python -m pytest -q tests/test_retitle.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.commands.catalog import handle_retitle
from eqsanscli.models.session_state import SessionState
from eqsanscli.services.matching_service import add_run_class_column, match_runs


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _state() -> SessionState:
    """A miniature IPTS-36552: three slot-named transmissions, three samples."""
    recs = [
        dict(run_number=181470, title="T-s1 4m 10A", detector_distance=4.0, wavelength=10.0, frequency=60),
        dict(run_number=181479, title="T-s10 4m 10A", detector_distance=4.0, wavelength=10.0, frequency=60),
        dict(run_number=181480, title="T-s11 4m 10A", detector_distance=4.0, wavelength=10.0, frequency=60),
        dict(run_number=181482, title="S-L62_0 4m 10A", detector_distance=4.0, wavelength=10.0, frequency=60),
        dict(run_number=181491, title="S-L121_0p24 4m 10A", detector_distance=4.0, wavelength=10.0, frequency=60),
        dict(run_number=181492, title="S-L62_l121 4m 10A", detector_distance=4.0, wavelength=10.0, frequency=60),
        dict(run_number=181518, title="S-L62_0 25C 4m 10A", detector_distance=4.0, wavelength=10.0, frequency=60),
        dict(run_number=181464, title="T-empty 4m 10A", detector_distance=4.0, wavelength=10.0, frequency=60),
    ]
    state = SessionState()
    state.ipts = 36552
    state.catalog = add_run_class_column(pd.DataFrame(recs))
    return state


def _title(state: SessionState, run: int) -> str:
    return next(str(r["title"]) for r in state.catalog_data if int(r["run_number"]) == run)


def test_single_run_retitle():
    state = _state()
    result = _run(handle_retitle(["181470", "T-L62_0", "4m", "10A"], state))
    assert result.success
    assert _title(state, 181470) == "T-L62_0 4m 10A"
    assert state.title_overrides["181470"]["original"] == "T-s1 4m 10A"


def test_word_swap_does_not_touch_s10_or_s11():
    """The bug this guards: a naive replace turns 'T-s10' into 'T-L62_00'."""
    state = _state()
    result = _run(handle_retitle(["s1", "L62_0"], state))
    assert result.success
    assert _title(state, 181470) == "T-L62_0 4m 10A"
    assert _title(state, 181479) == "T-s10 4m 10A"
    assert _title(state, 181480) == "T-s11 4m 10A"


def test_runs_spec_limits_the_swap():
    state = _state()
    _run(handle_retitle(["s10", "L121_0p24", "--runs", "181479"], state))
    assert _title(state, 181479) == "T-L121_0p24 4m 10A"
    assert _title(state, 181480) == "T-s11 4m 10A"


def test_unmatched_word_is_an_error_not_a_silent_noop():
    state = _state()
    result = _run(handle_retitle(["s42", "whatever"], state))
    assert not result.success
    assert "s42" in result.message


def test_matchruns_pairs_after_retitle():
    """The point of the whole command: the rows get their transmission."""
    state = _state()
    table, _ = match_runs(state.catalog, ipts=36552)
    assert [r.transmission_run for r in table.rows if r.sample_name == "L62_0"] == [""]

    _run(handle_retitle(["s1", "L62_0"], state))
    _run(handle_retitle(["s10", "L121_0p24"], state))
    _run(handle_retitle(["s11", "L62_l121"], state))
    table, _ = match_runs(state.catalog, ipts=36552)
    by_name = {r.sample_name: r.transmission_run for r in table.rows}
    assert by_name["L62_0"] == "181470"
    assert by_name["L121_0p24"] == "181479"
    assert by_name["L62_l121"] == "181480"
    # a temperature series matches the same transmission via the base name
    assert by_name["L62_0_25C"] == "181470"


def test_corrections_survive_a_catalog_reload():
    """ONCat keeps serving the original title; the correction goes back on top."""
    state = _state()
    _run(handle_retitle(["s1", "L62_0"], state))

    state.catalog = add_run_class_column(pd.DataFrame(
        [dict(run_number=181470, title="T-s1 4m 10A", detector_distance=4.0,
              wavelength=10.0, frequency=60)]))
    assert _title(state, 181470) == "T-s1 4m 10A"      # fresh fetch: wrong again
    assert state.apply_title_overrides() == 1
    assert _title(state, 181470) == "T-L62_0 4m 10A"


def test_clear_restores_the_oncat_title():
    state = _state()
    _run(handle_retitle(["181470", "T-L62_0", "4m", "10A"], state))
    _run(handle_retitle(["181470", "T-something-else", "4m", "10A"], state))
    result = _run(handle_retitle(["clear", "181470"], state))
    assert result.success
    assert _title(state, 181470) == "T-s1 4m 10A"      # the ONCat original, not the interim
    assert not state.title_overrides


def test_show_lists_corrections():
    state = _state()
    _run(handle_retitle(["s1", "L62_0"], state))
    result = _run(handle_retitle(["show"], state))
    assert result.success
    assert "181470" in result.message and "T-s1 4m 10A" in result.message


def test_overrides_round_trip_through_the_session_file(tmp_path):
    state = _state()
    _run(handle_retitle(["s1", "L62_0"], state))
    path = str(tmp_path / "sess.json")
    state.save(path)
    restored = SessionState.load(path)
    assert restored.title_overrides["181470"]["title"] == "T-L62_0 4m 10A"
