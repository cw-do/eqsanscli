"""/show table filters: --rows (index range), --name (substring), --sample (glob).

Requested: `/show table --rows 50-100` and `/show table --name 0.25phr` (rows
whose sample name contains 0.25phr). --name is a loose case-insensitive
substring match, distinct from --sample which is exact-or-glob. Filters combine.

    python -m pytest -q tests/test_show_table.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.commands.catalog import handle_show_table
from eqsanscli.models.session_state import SessionState
from eqsanscli.models.working_table import WorkingTableRow


def _state():
    st = SessionState()
    t = st.current_table
    named = [
        "70.30PBD_0.25phr_d0", "70.30PBD_0.25phr_d2",
        "other_sample", "70.30PBD_0.50phr_d0",
    ]
    for n in named:
        t.add_row(WorkingTableRow(
            index=0, scattering_run="0", sample_name=n,
            detector_distance=4.0, wavelength=2.5, frequency=30))
    for k in range(56):  # pad to 60 rows so 50-100 has content
        t.add_row(WorkingTableRow(
            index=0, scattering_run=str(2000 + k), sample_name=f"bulk_{k}",
            detector_distance=4.0, wavelength=2.5, frequency=30))
    return st


def _run(args, st):
    return asyncio.new_event_loop().run_until_complete(handle_show_table(args, st))


def _n(res):
    return len(res.data["rows"]) if res.data else 0


def test_no_filter_shows_all():
    st = _state()
    assert _n(_run([], st)) == 60


def test_name_is_substring_match():
    st = _state()
    res = _run(["--name", "0.25phr"], st)
    assert res.success
    assert _n(res) == 2  # the two _0.25phr_ rows, not the 0.50phr one


def test_name_is_case_insensitive():
    st = _state()
    assert _n(_run(["--name", "PBD"], st)) == 3


def test_rows_range():
    st = _state()
    assert _n(_run(["--rows", "50-100"], st)) == 11  # rows 50..60


def test_rows_list():
    st = _state()
    assert _n(_run(["--rows", "1,3,5"], st)) == 3


def test_filters_combine_and():
    st = _state()
    res = _run(["--rows", "1-3", "--name", "0.25phr"], st)
    assert _n(res) == 2  # rows 1-3 ∩ contains 0.25phr


def test_sample_glob_vs_exact():
    st = _state()
    assert _n(_run(["--sample", "*0.25phr*"], st)) == 2   # glob
    assert _n(_run(["--sample", "70.30PBD_0.25phr_d0"], st)) == 1  # exact


def test_no_match_is_success_with_message():
    st = _state()
    res = _run(["--name", "nomatch"], st)
    assert res.success and _n(res) == 0
    assert "No rows" in res.message


def test_unknown_flag_rejected():
    st = _state()
    res = _run(["--bogus", "5"], st)
    assert not res.success
    assert "Unrecognized" in res.message


def test_empty_table_message():
    res = _run(["--name", "x"], SessionState())
    assert res.success and "empty" in res.message.lower()


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
