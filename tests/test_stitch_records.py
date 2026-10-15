"""Records of what was done (v0.51.0; sansbook review B1–B3, B6, B7, B9, B10).

Before: the stitch factor was computed and discarded (merged file said `# I(Q)`
only), `/stitch run` returned a message, the stitch table was not saved, NOTE.md
held commands without results, headless data carried Rich markup, `/version`
returned a string, and `overlap auto` defaulted to 4 where its help said 6.

    python -m pytest -q tests/test_stitch_records.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from eqsanscli.commands.router import CommandResult
from eqsanscli.commands.stitch import handle_stitch
from eqsanscli.models.session_state import SessionState
from eqsanscli.services import note_service, scale_service
from eqsanscli.services.merge_service import StitchGroup, stitch_and_save


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _profiles(tmp: Path):
    """Low-Q profile I = 1/Q², high-Q profile twice that: the factor must be 0.5."""
    q1 = np.geomspace(0.003, 0.05, 60)
    q2 = np.geomspace(0.02, 0.4, 60)
    f1, f2 = tmp / "s1_8m12a_Iq.dat", tmp / "s1_4m2.5a_Iq.dat"
    for f, q, k in ((f1, q1, 1.0), (f2, q2, 2.0)):
        np.savetxt(f, np.c_[q, k / q**2, 0.01 * k / q**2], header="Q I dI")
    return [str(f1), str(f2)]


def test_merged_file_header_and_record_agree(tmp_path):
    files = _profiles(tmp_path)
    out = tmp_path / "merged_s1_8m12a_4m2.5a_Iq.txt"
    rec = stitch_and_save(files, ["8m12a", "4m2.5a"], [0.025, 0.04], 0, str(out), unit="a.u.")
    assert abs(rec["factors"][0] - 0.5) < 5e-3   # linear interp of 1/Q² on a log grid
    p = rec["pairs"][0]
    assert p["points_target"] > 0 and p["points_other"] > 0
    text = out.read_text()
    assert "target: 8m12a (index 0)" in text and "factor 0.49" in text
    assert "sha256" in text and "I in a.u." in text and "I (a.u.)" in text
    data = np.loadtxt(out, comments="#")             # header is skipped by readers
    assert data.shape[1] == 3


def test_stitch_factor_out_of_range_warns(tmp_path):
    files = _profiles(tmp_path)
    np.savetxt(files[1], np.c_[np.geomspace(0.02, 0.4, 60), np.full(60, 1e-6), np.full(60, 1e-8)])
    rec = stitch_and_save(files, ["8m12a", "4m2.5a"], [0.025, 0.04], 0,
                          str(tmp_path / "m.txt"))
    assert any("STC-05" in w for w in rec["warnings"])


def test_stitch_run_returns_data_and_the_table_persists(tmp_path):
    files = _profiles(tmp_path)
    st = SessionState()
    st.output_directory = str(tmp_path)
    st.configurations = {"8m12a": {"standardabsolutescale": 2.0}, "4m2.5a": {"standardabsolutescale": 0.4}}
    scale_service.record(st, "8m12a", "calibrate")
    scale_service.record(st, "4m2.5a", "calibrate")
    st.stitch_groups = [StitchGroup(sample_name="s1", files=files, configs=["8m12a", "4m2.5a"],
                                    overlaps=[0.025, 0.04], output_file=str(tmp_path / "m.txt"))]
    res = _run(handle_stitch(["run"], st))
    g = res.data["groups"][0]
    assert res.data["type"] == "stitch_result" and g["status"] == "done"
    assert abs(g["factors"][0] - 0.5) < 5e-3 and g["unit"] == "1/cm"
    p = st.save(str(tmp_path / "sess.json"))
    back = SessionState.load(p)
    assert back.stitch_groups[0].factors == st.stitch_groups[0].factors
    assert back.stitch_groups[0].status == "done"


def test_autopilot_records_what_it_stitched():
    from eqsanscli.services.autopilot import _record_stitch
    st = SessionState()
    st.stitch_groups = [StitchGroup(sample_name="s1", configs=["4m10a", "8m12a"], target_profile_index=0)]
    _record_stitch(st, "s1", {"files": ["a", "b"], "configs": ["8m12a", "4m10a"], "overlaps": [0.02, 0.03],
                              "target_index": 0, "output_file": "/o/m.txt", "factors": [1.01],
                              "pairs": [{"pair": [0, 1]}]})
    g = st.stitch_groups[0]
    assert g.configs[g.target_profile_index] == "8m12a" and g.output_file == "/o/m.txt"


def test_note_logs_results_not_just_commands():
    cal = CommandResult(success=True, data={
        "type": "calibration", "factor": 10.65, "qmin": 0.01, "qmax": 0.03, "n_points": 9,
        "std_rel": 0.006, "reference": "/r/NG3_B1_1413_4col.dat", "applied": True,
        "new_scale": 2.04, "porsil_scale": 0.1917, "config": "8m12a"})
    s = note_service.result_summary("calibrate", cal)
    assert "f=10.65" in s and "applied 2.04" in s and "8m12a" in s
    red = CommandResult(success=True, data={"type": "reduction_complete", "success": 3, "failed": 1,
                                            "results": [{"sample": "bad", "status": "error"}]})
    assert note_service.result_summary("reduce", red) == "3 done, 1 failed: bad"


def test_headless_data_has_no_markup():
    from eqsanscli.headless import _strip_data, _strip_markup
    out = _strip_data({"rows": [{"Scatt": "172760\n[dim]S-title[/dim]", "Src": "[bold cyan]*[/bold cyan]"}]})
    assert out["rows"][0] == {"Scatt": "172760\nS-title", "Src": "*"}
    assert _strip_markup("[4m2.5a30hz] ok") == "[4m2.5a30hz] ok"    # a label, not a tag


def test_version_is_data():
    from eqsanscli.version_info import version_info
    v = version_info()
    assert v["type"] == "version" and v["eqsanscli"] and "drtsans" in v


def test_overlap_auto_default_is_six():
    src = (REPO / "src/eqsanscli/commands/stitch.py").read_text()
    assert "n_points = 6" in src and "n_points = 4" not in src
