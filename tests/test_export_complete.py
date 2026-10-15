"""/export script reproduces the reduction (v0.53.0; sansbook review B8).

Before: a fixed list of ~25 parameters; any other non-default value
(logqbinsperdecade, normalization, wedges, timeslice offset …) was silently not
reproduced; files were named 2o5m2o5a instead of the CLI's 2.5m2.5a; no stitch.

Checked once by hand against IPTS-38269 (24 rows): the exported script, run in
the drtsans env with reduceNow replaced by EQVar's updateJsonFile, gave drtsans
jsons identical to eqsanscli's own for every row, bar the output dir and the
timestamp.

    python -m pytest -q tests/test_export_complete.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from eqsanscli.commands.export import handle_export_script
from eqsanscli.models.session_state import SessionState
from eqsanscli.models.working_table import WorkingTable, WorkingTableRow
from eqsanscli.services.merge_service import StitchGroup


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _state(tmp: Path) -> SessionState:
    st = SessionState()
    st.ipts = 12345
    st.output_directory = str(tmp)
    st.auto_instrument_files = False
    t = WorkingTable("default")
    t.rows = [WorkingTableRow(index=1, scattering_run="100", sample_name="s1", transmission_run="101",
                              empty_beam="102", detector_distance=2.5, wavelength=2.5, frequency=60)]
    st.tables = {"default": t}; st.active_table = "default"
    cfg = t.rows[0].configuration
    st.configurations = {cfg: {"logqbinsperdecade": 20, "normalization": "Monitor",
                               "numqbins": 150, "standardabsolutescale": 1.0}}
    return st


def test_every_non_default_parameter_is_exported(tmp_path):
    st = _state(tmp_path)
    out = tmp_path / "r.py"
    res = _run(handle_export_script([str(out)], st))
    assert res.success, res.message
    s = out.read_text()
    assert "eq._logqbinsperdecade = 20" in s          # not in the old fixed list
    assert "eq._normalization = 'Monitor'" in s
    assert "eq._numqbins = 150" in s
    assert "'_2.5m2.5a'" in s and "2o5" not in s      # the CLI's file names
    assert "# Absolute scale (2.5m2.5a): 1 (no standard calibrated" in s
    compile(s, str(out), "exec")


def test_stitch_block_from_the_session_table(tmp_path):
    st = _state(tmp_path)
    st.stitch_groups = [StitchGroup(sample_name="s1", files=["/o/s1_8m12a_Iq.dat", "/o/s1_2.5m2.5a_Iq.dat"],
                                    configs=["8m12a", "2.5m2.5a"], overlaps=[0.02, 0.03],
                                    target_profile_index=0, output_file="/o/merged_s1_Iq.txt")]
    out = tmp_path / "r.py"
    assert _run(handle_export_script([str(out), "--stitch"], st)).success
    s = out.read_text()
    assert "stitch_profiles(profiles, overlaps, target_profile_index=target)" in s
    assert "'/o/merged_s1_Iq.txt'" in s
    compile(s, str(out), "exec")


def test_stitch_without_a_table_is_refused(tmp_path):
    st = _state(tmp_path)
    assert not _run(handle_export_script([str(tmp_path / "r.py"), "--stitch"], st)).success
