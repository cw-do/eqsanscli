"""/trim and the stitch table's per-config trim (v0.54.0).

Checked once by hand on IPTS-38269's porsil (8m12a first 2, 4m2.5a last 5): the
`/export script --stitch` block run inside drtsans gave a merged file identical
to eqsanscli's own (128 rows, intensity difference 0). That check also found
v0.53.0's exported stitch block could not run at all: drtsans's load_iqmod
defaults to a space-separated pandas header, not the tab MantidAscii _Iq.dat.

    python -m pytest -q tests/test_trim.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from eqsanscli.commands.export import handle_export_script
from eqsanscli.commands.stitch import handle_stitch
from eqsanscli.commands.trim import handle_trim
from eqsanscli.models.session_state import SessionState
from eqsanscli.models.working_table import WorkingTable, WorkingTableRow
from eqsanscli.services.merge_service import StitchGroup
from eqsanscli.services.trim_service import TrimSpec, trim_mask


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _iq(path: Path, q, i, cols=4):
    with open(path, "w") as f:
        f.write("# I(Q)\n#Q (1/A)\tI (1/cm)\tdI (1/cm)" + ("\tdQ (1/A)" if cols == 4 else "") + "\n")
        for qq, ii in zip(q, i):
            row = [qq, ii, 0.1 * ii if np.isfinite(ii) else np.nan] + ([qq / 10] if cols == 4 else [])
            f.write("\t".join(f"{v:.6E}" for v in row) + "\n")
    return path


def test_nan_edge_rows_do_not_count():
    q = np.arange(1, 11) * 0.01
    i = np.array([np.nan, np.nan, 5, 4, 3, 2, 1, 0.5, np.nan, 0.0])
    r = trim_mask(q, i, TrimSpec(first=1, last=1))
    assert r.n_before == 6 and r.n_after == 4
    assert list(q[r.keep & np.isfinite(i) & (i != 0)]) == [0.04, 0.05, 0.06, 0.07]
    assert r.removed_low == [0.03, 0.03] and r.removed_high == [0.08, 0.08]


def test_trim_file_writes_beside_and_keeps_columns(tmp_path):
    src = _iq(tmp_path / "s1_4m10a_Iq.dat", np.arange(1, 21) * 0.01, np.linspace(20, 1, 20))
    before = src.read_text()
    st = SessionState(); st.output_directory = str(tmp_path)
    res = _run(handle_trim([str(src), "--first", "3", "--last", "2"], st))
    assert res.success, res.message
    out = tmp_path / "s1_4m10a_Iq_trim.dat"
    assert src.read_text() == before                         # original untouched
    text = out.read_text()
    assert "# trimmed: first 3, last 2" in text and text.splitlines()[-1].count("\t") == 3
    d = np.loadtxt(out, comments="#")
    assert len(d) == 15 and d[0, 0] == 0.04 and d[-1, 0] == 0.18
    assert res.data["files"][0]["n_after"] == 15


def test_q_limits_and_merged_three_column_files(tmp_path):
    m = _iq(tmp_path / "merged_s1_8m12a_4m2.5a_Iq.txt", np.geomspace(0.002, 0.5, 40),
            np.geomspace(100, 0.1, 40), cols=3)
    st = SessionState(); st.output_directory = str(tmp_path)
    assert _run(handle_trim(["merged_*_Iq.txt", "--qmin", "0.005", "--qmax", "0.3"], st)).success
    d = np.loadtxt(tmp_path / "merged_s1_8m12a_4m2.5a_Iq_trim.txt", comments="#")
    assert d[:, 0].min() >= 0.005 and d[:, 0].max() <= 0.3 and d.shape[1] == 3


def test_inplace_keeps_a_backup_and_patterns_skip_trim_outputs(tmp_path):
    src = _iq(tmp_path / "a_Iq.dat", np.arange(1, 11) * 0.01, np.linspace(10, 1, 10))
    st = SessionState(); st.output_directory = str(tmp_path)
    assert _run(handle_trim([str(src), "--last", "2", "--inplace"], st)).success
    assert (tmp_path / "a_Iq.dat.untrimmed").exists()
    assert len(np.loadtxt(src, comments="#")) == 8
    _run(handle_trim([str(src), "--last", "1"], st))
    res = _run(handle_trim([str(tmp_path / "*"), "--last", "1"], st))
    names = [Path(f["input"]).name for f in res.data["files"]]
    assert all(not n.endswith(".untrimmed") and "_trim" not in n for n in names)


def test_refusals(tmp_path):
    a = _iq(tmp_path / "a_Iq.dat", np.arange(1, 6) * 0.01, np.ones(5))
    b = _iq(tmp_path / "b_Iq.dat", np.arange(1, 6) * 0.01, np.ones(5))
    st = SessionState(); st.output_directory = str(tmp_path)
    assert not _run(handle_trim([str(a)], st)).success                         # nothing to trim
    assert not _run(handle_trim([str(a), "--frist", "2"], st)).success         # typo flag
    assert not _run(handle_trim([str(a), str(b), "--last", "1", "-o", "x.dat"], st)).success
    assert not _run(handle_trim([str(a), "--last", "9"], st)).success          # would empty it


def _stitch_state(tmp: Path) -> SessionState:
    q1, q2 = np.geomspace(0.003, 0.05, 50), np.geomspace(0.02, 0.4, 50)
    f1 = _iq(tmp / "s1_8m12a_Iq.dat", q1, 1 / q1**2)
    f2 = _iq(tmp / "s1_4m2.5a_Iq.dat", q2, 2 / q2**2)
    st = SessionState(); st.output_directory = str(tmp)
    st.stitch_groups = [StitchGroup(sample_name="s1", files=[str(f1), str(f2)], configs=["8m12a", "4m2.5a"],
                                    overlaps=[0.025, 0.04], output_file=str(tmp / "merged_s1_Iq.txt"))]
    return st


def test_stitch_trim_is_applied_and_recorded(tmp_path):
    st = _stitch_state(tmp_path)
    assert _run(handle_stitch(["set", "all", "trim", "4m2.5a", "--last", "5"], st)).success
    assert st.stitch_groups[0].trims == {"4m2.5a": {"last": 5}}
    res = _run(handle_stitch(["run"], st))
    g = res.data["groups"][0]
    assert g["trims"]["4m2.5a"]["n_after"] == 45
    text = (tmp_path / "merged_s1_Iq.txt").read_text()
    assert "trim 4m2.5a before stitching: last 5" in text
    assert np.loadtxt(tmp_path / "merged_s1_Iq.txt", comments="#")[:, 0].max() < 0.4 * 0.99
    show = _run(handle_stitch(["show"], st))
    assert "Trimmed before stitching" in show.message
    _run(handle_stitch(["set", "s1", "trim", "4m2.5a", "none"], st))
    assert st.stitch_groups[0].trims == {}


def test_stitch_trim_survives_save_and_rebuild(tmp_path, monkeypatch):
    from eqsanscli.commands import stitch as stitch_cmd
    st = _stitch_state(tmp_path)
    _run(handle_stitch(["set", "all", "trim", "8m12a", "--first", "2"], st))
    back = SessionState.load(st.save(str(tmp_path / "s.json")))
    assert back.stitch_groups[0].trims == {"8m12a": {"first": 2}}
    fresh = [StitchGroup(sample_name="s1", files=st.stitch_groups[0].files, configs=["8m12a", "4m2.5a"])]
    monkeypatch.setattr(stitch_cmd, "build_stitch_table", lambda table, out: fresh)
    _run(handle_stitch(["build"], st))
    assert st.stitch_groups[0].trims == {"8m12a": {"first": 2}}


def test_export_stitch_block_reads_mantid_ascii_and_trims(tmp_path):
    st = _stitch_state(tmp_path)
    st.ipts = 1
    st.auto_instrument_files = False
    t = WorkingTable("default")
    t.rows = [WorkingTableRow(index=1, scattering_run="1", sample_name="s1", empty_beam="2",
                              detector_distance=8, wavelength=12, frequency=60)]
    st.tables = {"default": t}; st.active_table = "default"
    st.stitch_groups[0].trims = {"4m2.5a": {"last": 5}}
    out = tmp_path / "r.py"
    assert _run(handle_export_script([str(out), "--stitch"], st)).success
    s = out.read_text()
    assert "header_type='MantidAscii'" in s and "sep='\\t'" in s
    assert "_trim(load_iqmod(" in s and "{'last': 5}" in s
    compile(s, str(out), "exec")


# --- /stitch build keeps what the user set (v0.54.1) ----------------------------
# IPTS-38077, 2026-10-15: /stitch set all overlap 0.05 0.06, then new runs were
# reduced and "stitch the newly reduced data" ran /stitch build — every sample
# went back to auto-suggested overlaps and the range had to be set again.

def test_rebuild_keeps_overlaps_and_gives_new_samples_the_all_choice(tmp_path, monkeypatch):
    from eqsanscli.commands import stitch as stitch_cmd
    cfgs = ["4m2.5a30hz_frame0", "4m2.5a30hz_frame1"]

    def build(names):
        return [StitchGroup(sample_name=n, files=[f"/o/{n}_0.dat", f"/o/{n}_1.dat"], configs=list(cfgs),
                            overlaps=[0.01, 0.02], target_profile_index=0) for n in names]

    st = SessionState(); st.output_directory = str(tmp_path)
    monkeypatch.setattr(stitch_cmd, "build_stitch_table", lambda t, o: build(["a06"]))
    _run(handle_stitch(["build"], st))
    _run(handle_stitch(["set", "all", "overlap", "0.05", "0.06"], st))
    _run(handle_stitch(["set", "a06", "target", "1"], st))          # per-sample choice
    st = SessionState.load(st.save(str(tmp_path / "s.json")))       # survives the session file

    monkeypatch.setattr(stitch_cmd, "build_stitch_table", lambda t, o: build(["a06", "EQ1-0"]))
    res = _run(handle_stitch(["build"], st))
    g = {x.sample_name: x for x in st.stitch_groups}
    assert g["a06"].overlaps == [0.05, 0.06] and g["a06"].target_profile_index == 1
    assert g["EQ1-0"].overlaps == [0.05, 0.06]                     # new sample: the 'all' choice
    assert "Kept your overlaps" in res.message and "EQ1-0" in res.message

    monkeypatch.setattr(stitch_cmd, "_auto_overlap_centered", lambda files, n: ([0.011, 0.021], "auto"))
    _run(handle_stitch(["set", "all", "overlap", "auto"], st))
    monkeypatch.setattr(stitch_cmd, "build_stitch_table", lambda t, o: build(["a06", "EQ1-0", "EQ2-0"]))
    _run(handle_stitch(["build"], st))
    g = {x.sample_name: x for x in st.stitch_groups}
    assert g["EQ2-0"].overlaps == [0.01, 0.02]                     # back to the builder's suggestion
