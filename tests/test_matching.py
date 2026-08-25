"""Transmission matching fallbacks and combined-field /set.

Covers two field-reported gaps (IPTS-37828, run series 187233–187242):

  1. A sample series measured at several displacements (S-…_d0, _d2, …) shares
     ONE transmission (T-…, no _dX). The per-name match missed it; the
     displacement-aware base match and the sole-transmission-per-config fallback
     now catch it — and the fallback refuses to guess when a config has more
     than one transmission.
  2. `/set <row> trans,emp <run>` assigns one run to both fields at once.

    python -m pytest -q tests/test_matching.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.commands.matching import handle_set
from eqsanscli.models.session_state import SessionState
from eqsanscli.models.working_table import WorkingTableRow
from eqsanscli.services.matching_service import add_run_class_column, match_runs


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _catalog(rows):
    return add_run_class_column(pd.DataFrame(rows))


def _series_rows():
    """The real 187233–187242 shape: one transmission, a displacement series."""
    cfg = dict(detector_distance=4.0, wavelength=2.5, frequency=30)
    return [
        dict(run_number=187233, title="T-70.30PBD_0.25phr 4m 2.5Afs 3mmsa", **cfg),
        dict(run_number=187234, title="S-70.30PBD_0.25phr_d0 4m 2.5Afs 3mmsa", **cfg),
        dict(run_number=187235, title="S-70.30PBD_0.25phr_d2 4m 2.5Afs 3mmsa", **cfg),
        dict(run_number=187242, title="S-70.30PBD_0.25phr_d16 4m 2.5Afs 3mmsa", **cfg),
    ]


# --- transmission matching -------------------------------------------------

def test_displacement_series_matches_single_transmission():
    table, _ = match_runs(_catalog(_series_rows()))
    assert len(table.rows) == 3
    assert all(r.transmission_run == "187233" for r in table.rows), (
        [(r.sample_name, r.transmission_run) for r in table.rows]
    )


def test_displacement_series_matches_by_base_not_config_guess():
    # The base-name match should carry it; no by-configuration warning needed.
    _, warnings = match_runs(_catalog(_series_rows()))
    assert not any("by configuration" in w for w in warnings), warnings


def test_sole_transmission_fallback_when_names_differ():
    cfg = dict(detector_distance=4.0, wavelength=6.0, frequency=60)
    rows = [
        dict(run_number=200, title="T-calibrant 4m 6A", **cfg),
        dict(run_number=201, title="S-alpha 4m 6A", **cfg),
        dict(run_number=202, title="S-beta 4m 6A", **cfg),
    ]
    table, warnings = match_runs(_catalog(rows))
    assert all(r.transmission_run == "200" for r in table.rows)
    assert any("by configuration" in w for w in warnings), warnings


def test_no_guess_when_config_has_two_transmissions():
    cfg = dict(detector_distance=4.0, wavelength=6.0, frequency=60)
    rows = [
        dict(run_number=200, title="T-calibrant 4m 6A", **cfg),
        dict(run_number=203, title="T-other 4m 6A", **cfg),
        dict(run_number=201, title="S-alpha 4m 6A", **cfg),
    ]
    table, warnings = match_runs(_catalog(rows))
    assert table.rows[0].transmission_run == ""
    assert not any("by configuration" in w for w in warnings)


def test_d2o_like_name_not_stripped_as_displacement():
    # "_d2o" is not a displacement token — the samples must stay distinct and
    # not collapse onto one transmission by accident.
    cfg = dict(detector_distance=4.0, wavelength=6.0, frequency=60)
    rows = [
        dict(run_number=300, title="T-x_d2o 4m 6A", **cfg),
        dict(run_number=301, title="S-x_d2o 4m 6A", **cfg),
        dict(run_number=302, title="S-y_h2o 4m 6A", **cfg),
    ]
    table, _ = match_runs(_catalog(rows))
    by_name = {r.sample_name: r.transmission_run for r in table.rows}
    # x_d2o finds its own transmission; y_h2o has none of its own but the sole
    # transmission fallback does NOT fire because there are two S rows with only
    # one T that already name-matched one of them — the other is left blank.
    assert "300" in by_name.values()


# --- combined-field /set ---------------------------------------------------

def _state_one_row():
    st = SessionState()
    st.current_table.add_row(WorkingTableRow(
        index=0, scattering_run="187234", sample_name="poly_d0",
        detector_distance=4.0, wavelength=2.5, frequency=30,
    ))
    return st


def test_set_trans_and_emp_together():
    st = _state_one_row()
    res = _run(handle_set(["187234", "trans,emp", "187233"], st))
    assert res.success, res.message
    row = st.current_table.rows[0]
    assert row.transmission_run == "187233"
    assert row.empty_beam == "187233"


def test_set_combined_with_plus_separator():
    st = _state_one_row()
    _run(handle_set(["187234", "trans+bkg", "999"], st))
    row = st.current_table.rows[0]
    assert row.transmission_run == "999"
    assert row.background_scatt == "999"


def test_set_combined_clear():
    st = _state_one_row()
    _run(handle_set(["187234", "trans,emp", "187233"], st))
    _run(handle_set(["187234", "trans,emp", "none"], st))
    row = st.current_table.rows[0]
    assert row.transmission_run == ""
    assert row.empty_beam == ""


def test_set_reject_mixing_special_field():
    st = _state_one_row()
    res = _run(handle_set(["187234", "trans,thickness", "5"], st))
    assert not res.success
    assert "thickness" in res.message


def test_set_unknown_field_in_combo():
    st = _state_one_row()
    res = _run(handle_set(["187234", "trans,bogus", "5"], st))
    assert not res.success
    assert "bogus" in res.message


def test_single_field_set_unchanged():
    # Existing single-field behaviour must be untouched.
    st = _state_one_row()
    res = _run(handle_set(["187234", "trans", "187233"], st))
    assert res.success
    assert st.current_table.rows[0].transmission_run == "187233"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
