"""Stale calibrations and kept session state (v0.50.0; SCL-05, sansbook review A4/A6).

A4: a calibration fits only the reduction it came from — change the mask, the Q
binning, the incoherent fit… and the scale is stale. Nothing said so.
A6: IPTS-37953's 56-row session was found replaced by an empty autosave with no
copy; the only full record was a file autopilot happened to write.

    python -m pytest -q tests/test_records.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from eqsanscli.commands.calibrate import handle_calibrate
from eqsanscli.commands.check import handle_check
from eqsanscli.commands.config import handle_set_config
from eqsanscli.commands.session import handle_continue
from eqsanscli.models.session_state import SessionState
from eqsanscli.models.working_table import WorkingTable, WorkingTableRow
from eqsanscli.services import scale_service

REF = REPO / "absscale_reference" / "NG3_B1_1413_4col.dat"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _porsil(tmp: Path, cfg: str, mask: str):
    d = np.loadtxt(REF, comments="#")
    with open(tmp / f"porsil_{cfg}_Iq.dat", "w") as fh:
        for q, i, di in d[:, :3]:
            fh.write(f"{q:.6E}\t{i / 2:.6E}\t{di / 2:.6E}\n")
    (tmp / f"porsil_{cfg}.json").write_text(json.dumps({"configuration": {
        "StandardAbsoluteScale": 1.0, "maskFileName": mask, "numQbins": 120}}))
    return tmp / f"porsil_{cfg}_Iq.dat"


# --- A4: stale calibration -------------------------------------------------------

def test_mask_change_makes_the_calibration_stale_and_recalibrating_clears_it(tmp_path):
    st = SessionState()
    st.output_directory = str(tmp_path)
    st.configurations["8m12a"] = {"maskfilename": "/m/a.nxs", "numqbins": 120}
    meas = _porsil(tmp_path, "8m12a", "/m/a.nxs")
    _run(handle_calibrate([str(meas), "--applynow"], st))
    assert scale_service.stale_reason(st, "8m12a") == ""

    _run(handle_set_config(["8m12a", "maskfilename", "/m/b.nxs"], st))
    reason = scale_service.stale_reason(st, "8m12a")
    assert "maskfilename" in reason
    assert "STALE" in scale_service.describe(st, "8m12a")
    t = WorkingTable("default")
    t.rows = [WorkingTableRow(index=1, scattering_run="9", sample_name="s", empty_beam="1",
                              detector_distance=8, wavelength=12, frequency=60)]
    st.tables = {"default": t}; st.active_table = "default"
    rules = {f["rule"] for f in _run(handle_check([], st)).data["findings"]}
    assert "SCL-05" in rules

    meas = _porsil(tmp_path, "8m12a", "/m/b.nxs")       # standard re-reduced with the new mask
    _run(handle_calibrate([str(meas), "--applynow"], st))
    assert scale_service.stale_reason(st, "8m12a") == ""


# --- A6: session state kept -----------------------------------------------------

def _with_rows(st: SessionState, n: int) -> SessionState:
    t = WorkingTable("default")
    t.rows = [WorkingTableRow(index=i + 1, scattering_run=str(100 + i), sample_name=f"s{i}")
              for i in range(n)]
    st.tables = {"default": t}; st.active_table = "default"
    return st


def test_emptying_a_session_keeps_the_previous_autosave(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    auto = SessionState.auto_save_path()
    st = _with_rows(SessionState(), 56)
    st.ipts = 37953
    st.save(auto)
    st.tables["default"].rows[0].sample_name = "renamed"     # an edit: same shape
    st.save(auto)
    assert not os.path.exists(auto.replace(".json", ".1.json"))
    _with_rows(st, 0).save(auto)                              # rows gone
    kept = json.load(open(auto.replace(".json", ".1.json")))
    assert len(kept["tables"]["default"]["rows"]) == 56


def test_generations_are_bounded(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    auto = SessionState.auto_save_path()
    st = SessionState()
    for n in range(1, 10):
        _with_rows(st, n).save(auto)
    base = auto[: -len(".json")]
    assert os.path.exists(f"{base}.5.json") and not os.path.exists(f"{base}.6.json")


def test_reduction_snapshot_is_written_beside_the_outputs(tmp_path):
    st = _with_rows(SessionState(), 3)
    st.output_directory = str(tmp_path)
    p = st.snapshot_for_reduction()
    assert p and Path(p).parent == tmp_path / ".eqsanscli_reduce"
    assert len(json.load(open(p))["tables"]["default"]["rows"]) == 3


def test_continue_will_not_replace_rows_with_another_folders_state(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    other = tmp_path / "IPTS-11111" / "shared"
    here = tmp_path / "IPTS-22222" / "shared"
    other.mkdir(parents=True); here.mkdir(parents=True)
    monkeypatch.chdir(other)
    st = _with_rows(SessionState(), 5); st.ipts = 11111
    st.save(SessionState.auto_save_path())                   # breadcrumb → other folder
    monkeypatch.chdir(here)
    mine = _with_rows(SessionState(), 2); mine.ipts = 22222
    res = _run(handle_continue([], mine))
    assert not res.success and "--force" in res.message
    assert len(mine.current_table.rows) == 2                  # untouched
    res = _run(handle_continue(["--force"], mine))
    assert res.success and "another folder" in res.message and "IPTS-22222" in res.message
