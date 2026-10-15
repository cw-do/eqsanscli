"""Absolute scale: provenance, presets, /calibrate (v0.48.0; protocol SCL-01..04).

From the sansbook review (2026-10-15, A2/A3), verified on disk:
  * IPTS-37953 had no standard, yet every row carried 0.1916573 — a 4 m 10 Å
    preset's factor from another experiment — and the files said 1/cm.
  * `/calibrate --applynow` set f alone; f is relative to the scale the porsil
    was reduced with, so a porsil reduced at 0.1917 gave 10.65 instead of 2.04.
  * `…30hz_frame_0_Iq.dat` never parsed; a missing/typo'd reference silently
    became NG3; unknown flags were ignored.

    python -m pytest -q tests/test_scale.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from eqsanscli.commands.calibrate import handle_calibrate
from eqsanscli.commands.config import handle_set_config, handle_show_config
from eqsanscli.commands.matching import handle_matchruns
from eqsanscli.commands.preset import handle_apply_preset
from eqsanscli.models.session_state import SessionState
from eqsanscli.services import scale_service
from eqsanscli.services.config_manager import _load_matching_preset
from eqsanscli.services.matching_service import add_run_class_column
from eqsanscli.services.preset_service import find_closest_preset, list_presets

REF = REPO / "absscale_reference" / "NG3_B1_1413_4col.dat"


def _run(coro):
    loop = asyncio.new_event_loop()   # own loop: another test's asyncio.run() leaves none
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _porsil(tmp: Path, stem: str, f_true: float, s0: float | None, suffix="_Iq.dat"):
    """A measured standard that is exactly the reference / f_true, with its input json."""
    d = np.loadtxt(REF, comments="#")
    with open(tmp / f"{stem}{suffix}", "w") as fh:
        fh.write("#Q (1/A)\tI (1/cm)\tdI (1/cm)\n")
        for q, i, di in d[:, :3]:
            fh.write(f"{q:.6E}\t{i / f_true:.6E}\t{di / f_true:.6E}\n")
    if s0 is not None:
        (tmp / f"{stem}.json").write_text(json.dumps(
            {"outputFileName": stem, "configuration": {"StandardAbsoluteScale": s0}}))
    return tmp / f"{stem}{suffix}"


def _state(tmp: Path) -> SessionState:
    st = SessionState()
    st.output_directory = str(tmp)
    return st


# --- /calibrate ---------------------------------------------------------------

def test_applynow_compounds_with_the_scale_the_porsil_was_reduced_with(tmp_path):
    f_true, s0 = 10.65, 0.1916573
    meas = _porsil(tmp_path, "porsil_8m12a", f_true, s0)
    st = _state(tmp_path)
    res = _run(handle_calibrate([str(meas), "--applynow"], st))
    assert res.success, res.message
    d = res.data
    assert d["type"] == "calibration" and d["applied"] and d["config"] == "8m12a"
    assert abs(d["factor"] - f_true) / f_true < 1e-4
    assert abs(st.configurations["8m12a"]["standardabsolutescale"] - s0 * f_true) < 1e-3
    assert d["std_rel"] < 1e-3                       # flat ratio: exact copy of the reference
    p = scale_service.provenance(st, "8m12a")
    assert p["kind"] == "calibrate" and p["porsil_scale_at_calibration"] == s0
    assert (tmp_path / "calibration_8m12a.json").exists()
    assert (tmp_path / "calibration_history.jsonl").read_text().count("\n") == 1
    assert scale_service.unit(st, "8m12a") == "1/cm"


def test_frame_skipping_files_parse_and_apply(tmp_path):
    meas = _porsil(tmp_path, "porsil_4m2.5a30hz", 2.0, 1.0, suffix="_frame_0_Iq.dat")
    st = _state(tmp_path)
    res = _run(handle_calibrate([str(meas), "--applynow"], st))
    assert res.data["config"] == "4m2.5a30hz" and res.data["applied"], res.message


def test_applynow_refuses_without_the_input_json(tmp_path):
    meas = _porsil(tmp_path, "porsil_4m10a", 3.0, None)
    st = _state(tmp_path)
    res = _run(handle_calibrate([str(meas), "--applynow"], st))
    assert res.success and not res.data["applied"]
    assert "standardabsolutescale" not in st.configurations.get("4m10a", {})


def test_unknown_reference_and_flags_are_errors(tmp_path):
    meas = _porsil(tmp_path, "porsil_4m10a", 3.0, 1.0)
    st = _state(tmp_path)
    assert not _run(handle_calibrate([str(meas), "--ref", "NG9"], st)).success
    assert not _run(handle_calibrate([str(meas), "--qmax0.05"], st)).success
    assert not _run(handle_calibrate([str(meas), "--qmin", "x"], st)).success


# --- presets never carry a scale ------------------------------------------------

def test_presets_carry_no_scale(tmp_path):
    names = [p["name"] for p in list_presets()]
    assert any("4m_10a" in n for n in names)
    assert "standardabsolutescale" not in _load_matching_preset("4m10a")
    st = _state(tmp_path)
    res = _run(handle_apply_preset(["conf_4m_10a_60hz", "4m10a"], st))
    assert res.success
    assert scale_service.current_scale(st, "4m10a") == 1.0
    assert scale_service.unit(st, "4m10a") == "a.u."


def test_users_own_json_scale_is_kept_as_user(tmp_path):
    js = tmp_path / "mine.json"
    js.write_text(json.dumps({"configuration": {"StandardAbsoluteScale": 0.38, "numQbins": 100}}))
    st = _state(tmp_path)
    res = _run(handle_apply_preset([str(js), "4m10a"], st))
    assert res.success, res.message
    assert scale_service.current_scale(st, "4m10a") == 0.38
    assert scale_service.provenance(st, "4m10a")["kind"] == "user"


def test_inexact_preset_prefers_same_wavelength():
    names = [p["name"] for p in list_presets()]
    best, kind = find_closest_preset("4m2.5a30hz", names)
    assert kind == "distance" and "2.5a" in best.replace("_", "")


# --- /set config, /show config, /matchruns ----------------------------------------

def test_set_scale_records_user_and_one_is_relative(tmp_path):
    st = _state(tmp_path)
    _run(handle_set_config(["4m10a", "standardabsolutescale", "0.38"], st))
    assert scale_service.provenance(st, "4m10a")["kind"] == "user"
    show = _run(handle_show_config(["4m10a"], st))
    assert show.data["scale"]["unit"] == "1/cm" and "user" in show.data["scale"]["text"]
    _run(handle_set_config(["4m10a", "standardabsolutescale", "1.0"], st))
    assert scale_service.unit(st, "4m10a") == "a.u."
    res = _run(handle_set_config(["4m10a", "standardabsolutescale", "120"], st))
    assert "0.01–50" in res.message


def test_unknown_origin_is_flagged(tmp_path):
    st = _state(tmp_path)
    st.configurations["4m10a"] = {"standardabsolutescale": 0.1916573}   # pre-0.48 session
    assert scale_service.is_relative(st, "4m10a") is None
    assert "origin unknown" in scale_service.describe(st, "4m10a")


def test_fresh_match_without_standard_is_relative(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    st = _state(tmp_path)
    st.catalog = add_run_class_column(pd.DataFrame([
        dict(run_number=100 + i, title=t, detector_distance=4.0, wavelength=2.5, frequency=30)
        for i, t in enumerate(["T-empty beam 4m 2.5a", "T-sebs 4m 2.5a", "S-sebs 4m 2.5a"])]))
    res = _run(handle_matchruns([], st))
    assert res.success, res.message
    cfg = st.current_table.configurations[0]
    assert scale_service.current_scale(st, cfg) == 1.0
    assert scale_service.provenance(st, cfg)["kind"] == "default"
    assert "relative (a.u.)" in res.message


def test_plot_label_follows_the_unit(tmp_path):
    from eqsanscli.commands.data import _set_intensity_unit
    from eqsanscli.services.plotting_service import PlotOptions
    st = _state(tmp_path)
    st.configurations["4m2.5a30hz"] = {"standardabsolutescale": 1.0}
    st.configurations["8m12a"] = {"standardabsolutescale": 2.04}
    scale_service.record(st, "8m12a", "calibrate")
    o = PlotOptions()
    _set_intensity_unit(o, ["s1_4m2.5a30hz_frame_0_Iq.dat"], st)
    assert "a.u." in o.ylabel
    o = PlotOptions()
    _set_intensity_unit(o, ["s1_8m12a_Iq.dat"], st)
    assert o.ylabel is None                     # default 1/cm label stays
