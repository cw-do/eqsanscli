"""Transmission pairing and /check (v0.49.0; protocol TBL-02, TBL-06, TBL-09).

From the sansbook review (2026-10-15, A5/B4), checked on IPTS-37953's catalog:
56 rows reduced with no transmission because the displacement was written with
dashes (`S-sebs-5wt-SiNPs--d26`), while 13 transmission runs sat unused. The fix
pairs a dash *series* only — a lone `PS-d8` is a deuteration label. A missing
transmission still never blocks /reduce (owner); it is reported instead.

    python -m pytest -q tests/test_transmission_pairing.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.commands.check import handle_check
from eqsanscli.commands.matching import handle_matchruns
from eqsanscli.commands.reduction import handle_reduce
from eqsanscli.models.session_state import SessionState
from eqsanscli.models.working_table import WorkingTable, WorkingTableRow
from eqsanscli.services import protocol
from eqsanscli.services.matching_service import add_run_class_column, match_runs

_TITLES = [
    "T-empty beam 4m 2.5Afs",
    "T-sebs-5wt-SiNPs 4m 2.5Afs 5mmsa",
    "T-sebs-5wt-sinp 4m 2.5Afs 5mmsa",
    "T-PS 4m 2.5Afs",
    "T-orphan 4m 2.5Afs",
    "S-sebs-5wt-SiNPs--d0 4m 2.5Afs 5mmsa",
    "S-sebs-5wt-SiNPs--d26 4m 2.5Afs 5mmsa",
    "S-sebs-5wt-sinp-d0 4m 2.5Afs 5mmsa",
    "S-sebs-5wt-sinp-d40 4m 2.5Afs 5mmsa",
    "S-PS-d8 4m 2.5Afs",
    "S-PS 4m 2.5Afs",
    "S-orphanage-d0 4m 2.5Afs",
]


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def _cat(titles=_TITLES):
    return add_run_class_column(pd.DataFrame([
        dict(run_number=100 + i, title=t, detector_distance=4.0, wavelength=2.5, frequency=30)
        for i, t in enumerate(titles)]))


def _trans(table):
    return {r.sample_name: r.transmission_run for r in table.rows}


def test_dash_displacement_series_pairs():
    t = _trans(match_runs(_cat())[0])
    assert t["sebs-5wt-SiNPs--d0_5mmsa"] == t["sebs-5wt-SiNPs--d26_5mmsa"] == "101"
    assert t["sebs-5wt-sinp-d0_5mmsa"] == t["sebs-5wt-sinp-d40_5mmsa"] == "102"


def test_lone_deuteration_label_does_not_borrow():
    t = _trans(match_runs(_cat())[0])
    assert t["PS"] == "103"
    assert t["PS-d8"] == ""             # not PS's transmission


def test_base_matches_are_reported():
    _, warnings = match_runs(_cat())
    assert any("condition token ignored" in w and "4 row(s)" in w for w in warnings)


def test_matchruns_reports_unused_transmissions(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    st = SessionState()
    st.output_directory = str(tmp_path)
    st.catalog = _cat()
    res = _run(handle_matchruns([], st))
    rep = res.data["transmission_report"]
    unused = {u["run"]: u for u in rep["unused"]}
    assert "104" in unused                       # T-orphan
    assert unused["104"]["closest_names"] == ["orphanage-d0"]
    assert "transmission run(s) unused" in res.message


def test_tbl06_allows_background_cells_but_not_self_background():
    rows = [
        WorkingTableRow(index=1, scattering_run="10", sample_name="cup", transmission_run="11",
                        empty_beam="1", detector_distance=4, wavelength=2.5, frequency=60),
        WorkingTableRow(index=2, scattering_run="20", sample_name="s", transmission_run="21",
                        background_scatt="10", background_trans="11", empty_beam="1",
                        detector_distance=4, wavelength=2.5, frequency=60),
    ]
    st = SessionState()
    t = WorkingTable("default"); t.rows = rows
    st.tables = {"default": t}; st.active_table = "default"
    assert not [f for f in protocol.check(st) if f.rule == "TBL-06"]
    rows[1].background_scatt = "20"             # its own background
    assert [f for f in protocol.check(st) if f.rule == "TBL-06"]


def _table_state(**row_kw):
    st = SessionState()
    t = WorkingTable("default")
    t.rows = [WorkingTableRow(index=1, scattering_run="20", sample_name="s", empty_beam="1",
                              detector_distance=4, wavelength=2.5, frequency=60, **row_kw)]
    st.tables = {"default": t}; st.active_table = "default"
    return st


def test_missing_transmission_never_blocks_reduce(tmp_path):
    st = _table_state()                          # no transmission, no background
    st.output_directory = str(tmp_path)
    res = _run(handle_reduce(["all"], st))
    assert res.success and res.data["type"] == "start_reduction", res.message


def test_blocking_protocol_finding_stops_reduce_unless_forced(tmp_path):
    st = _table_state(background_scatt="20", background_trans="21")   # own background
    st.output_directory = str(tmp_path)
    res = _run(handle_reduce(["all"], st))
    assert not res.success and "BKG-02" in res.message
    assert _run(handle_reduce(["all", "--force"], st)).success


def test_check_returns_findings_as_data(tmp_path):
    st = _table_state()
    st.tables["default"].rows[0].empty_beam = ""
    res = _run(handle_check([], st))
    rules = {f["rule"]: f for f in res.data["findings"]}
    assert rules["EMP-01"]["severity"] == "blocking" and rules["EMP-01"]["rows"] == [1]
    assert "TBL-02" in rules
    assert res.data["unenforced"]
