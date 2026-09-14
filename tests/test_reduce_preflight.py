"""Preflight checks before reduction — an empty beam is mandatory.

`json_builder` puts `empty_beam` in BOTH `beamCenter.runNumber` and
`emptyTransmission.runNumber`, so a row without one has no beam centre and
cannot reduce. `/reduce` used to pass such rows straight to drtsans, which
failed per row with an opaque error.

    python tests/test_reduce_preflight.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.commands.reduction import handle_reduce
from eqsanscli.models.session_state import SessionState
from eqsanscli.models.working_table import WorkingTableRow
from eqsanscli.services.reduction_service import (
    advisory_problems, blocking_problems, preflight,
)


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _row(index, sample, **kw):
    defaults = dict(
        scattering_run=str(186500 + index), sample_name=sample,
        detector_distance=4.0, wavelength=10.0, frequency=60,
    )
    defaults.update(kw)
    return WorkingTableRow(index=0, **defaults)


def _state():
    """Rows 1 complete, 2 and 3 without an empty beam, 4 missing only optionals."""
    state = SessionState()
    state.ipts = 38773
    table = state.current_table
    table.add_row(_row(1, "Good", transmission_run="186521",
                       background_scatt="186530", empty_beam="186517"))
    table.add_row(_row(2, "NoEmp", transmission_run="186523", wavelength=2.5))
    table.add_row(_row(3, "NoEmp2", detector_distance=1.3, wavelength=2.5))
    table.add_row(_row(4, "NoTrans", empty_beam="186517"))
    return state


# --- classification -------------------------------------------------------

def test_missing_empty_beam_blocks():
    row = _row(1, "X", empty_beam="")
    assert any("empty beam" in p for p in blocking_problems(row))


def test_missing_scattering_run_blocks():
    row = _row(1, "X", scattering_run="", empty_beam="186517")
    assert any("scattering run" in p for p in blocking_problems(row))


def test_complete_row_has_no_problems():
    row = _row(1, "X", transmission_run="1", background_scatt="2", empty_beam="3")
    assert blocking_problems(row) == []
    assert advisory_problems(row) == []


def test_transmission_and_background_are_advisory_only():
    row = _row(1, "X", empty_beam="186517")
    assert blocking_problems(row) == []
    problems = advisory_problems(row)
    assert any("transmission" in p for p in problems)
    assert any("background" in p for p in problems)


def test_bad_thickness_is_advisory():
    assert any("thickness" in p for p in advisory_problems(
        _row(1, "X", empty_beam="1", thickness=0)))


def test_preflight_splits_rows():
    state = _state()
    blocked, advisory = preflight(state.current_table.rows)
    assert [r.sample_name for r, _ in blocked] == ["NoEmp", "NoEmp2"]
    assert [r.sample_name for r, _ in advisory] == ["NoTrans"]


# --- /reduce behaviour ----------------------------------------------------

def test_reduce_refuses_when_a_row_cannot_reduce():
    result = _run(handle_reduce(["all"], _state()))
    assert result.success is False
    assert result.data is None                      # reduction never starts
    assert "cannot be reduced" in result.message
    assert "no empty beam" in result.message
    # names the configurations and the ways to fix it
    assert "4m2.5a" in result.message and "1.3m2.5a" in result.message
    assert "/reclass <run> empty" in result.message
    assert "/set --config <id> emp <run>" in result.message


def test_reduce_skip_missing_reduces_the_rest():
    result = _run(handle_reduce(["all", "--skip-missing"], _state()))
    assert result.success is True
    assert result.data["indices"] == [1, 4]
    assert "Skipping 2 row(s)" in result.message


def test_reduce_force_sends_everything():
    result = _run(handle_reduce(["all", "--force"], _state()))
    assert result.success is True
    assert result.data["indices"] == [1, 2, 3, 4]
    assert "--force" in result.message


def test_reduce_clean_row_is_silent():
    result = _run(handle_reduce(["1"], _state()))
    assert result.success is True
    assert result.data["indices"] == [1]
    assert result.message == ""


def test_reduce_advisory_only_proceeds_with_a_warning():
    result = _run(handle_reduce(["4"], _state()))
    assert result.success is True
    assert result.data["indices"] == [4]
    assert "missing optional fields" in result.message


def test_reduce_skip_missing_with_nothing_left_fails():
    result = _run(handle_reduce(["2", "--skip-missing"], _state()))
    assert result.success is False
    assert "Nothing left to reduce" in result.message


def test_flags_do_not_break_selection_parsing():
    result = _run(handle_reduce(["--sample", "Good", "--force"], _state()))
    assert result.success is True
    assert result.data["indices"] == [1]

    result = _run(handle_reduce(["--new", "--skip-missing"], _state()))
    assert result.success is True
    assert result.data["indices"] == [1, 4]


def test_flags_alone_are_rejected():
    result = _run(handle_reduce(["--force"], _state()))
    assert result.success is False
    assert "Give rows to reduce" in result.message


def test_help_mentions_the_new_flags():
    result = _run(handle_reduce([], _state()))
    assert "--skip-missing" in result.message and "--force" in result.message


# --- autopilot's low-level guard ------------------------------------------

def test_autopilot_reduce_phase_skips_unreducible_rows():
    """_reduce_phase must not hand a beam-centre-less row to drtsans."""
    from eqsanscli.services import autopilot

    state = _state()
    written: list[str] = []
    calls: list[str] = []

    def fake_reduce_row(**kwargs):
        calls.append(kwargs["row"].sample_name)
        class _R:
            success, cancelled, elapsed_seconds = True, False, 1.0
            output_file, log_file, err_file, note = "out.dat", "", "", ""
        return _R()

    import eqsanscli.services.reduction_service as rs
    original = rs.reduce_row
    rs.reduce_row = fake_reduce_row
    try:
        autopilot._reduce_phase(
            rows=list(state.current_table.rows), state=state, output_dir="/tmp",
            write=written.append, cancel_event=None, max_workers=1,
        )
    finally:
        rs.reduce_row = original

    assert calls == ["Good", "NoTrans"]           # the two reducible rows only
    assert any("skipped" in line for line in written)
    assert any("NoEmp" in line for line in written)


# --- output directory must be writable (a bad /set outputdir must not crash) --
# Reported: setting outputdir to a folder without write permission crashed
# eqsanscli mid-reduction (PermissionError escaped the worker). Now: refuse up
# front, and reduce_row fails the row cleanly instead of raising.

import os
import stat
import tempfile

from eqsanscli.services.reduction_service import output_dir_problem, reduce_row


def _readonly_dir():
    d = tempfile.mkdtemp()
    os.chmod(d, stat.S_IRUSR | stat.S_IXUSR)   # r-x: cannot create files
    return d


def test_output_dir_problem_passes_writable_and_creatable():
    d = tempfile.mkdtemp()
    assert output_dir_problem(d) is None                       # existing, writable
    assert output_dir_problem(os.path.join(d, "a", "b")) is None  # will be created


def test_output_dir_problem_flags_readonly_and_file():
    ro = _readonly_dir()
    try:
        assert "permission denied" in output_dir_problem(ro)
        assert "permission denied" in output_dir_problem(os.path.join(ro, "sub"))
    finally:
        os.chmod(ro, 0o700)
    f = tempfile.NamedTemporaryFile(delete=False)
    f.close()
    assert "not a directory" in output_dir_problem(f.name)


def test_reduce_row_does_not_crash_on_unwritable_dir():
    ro = _readonly_dir()
    try:
        row = _row(1, "X", empty_beam="99")
        result = reduce_row(row=row, ipts=1, user_configs={},
                            output_dir=os.path.join(ro, "out"))
        assert result.success is False           # failed, not raised
        assert "Cannot write" in result.stderr
        assert row.status == "error"
    finally:
        os.chmod(ro, 0o700)


def test_reduce_refuses_unwritable_output_dir_up_front():
    ro = _readonly_dir()
    try:
        state = _state()
        state.output_directory = ro
        result = _run(handle_reduce(["1"], state))
        assert result.success is False
        assert result.data is None               # reduction never starts
        assert "output directory" in result.message and "permission denied" in result.message
        assert "/set outputdir" in result.message
    finally:
        os.chmod(ro, 0o700)


def test_autopilot_reduce_phase_stops_on_unwritable_dir():
    from eqsanscli.services import autopilot
    ro = _readonly_dir()
    try:
        state = _state()
        written: list[str] = []
        n_ok, n_fail = autopilot._reduce_phase(
            rows=[r for r in state.current_table.rows if r.sample_name == "Good"],
            state=state, output_dir=ro,
            write=written.append, cancel_event=None, max_workers=1,
        )
        assert n_ok == 0 and n_fail == 1
        assert any("Cannot reduce" in line and "permission denied" in line for line in written)
    finally:
        os.chmod(ro, 0o700)


# --- a GUI/display crash AFTER a complete reduction is not a failure ---------
# IPTS-38151 a20a0-1_fs: a 62-min time-slice reduction wrote all 242 I(Q) files,
# then drtsans exited nonzero on an interactive-Qt-under-simple-prompt / dropped-
# X11 teardown ("Cannot install event loop hook", "ICE default IO error handler
# ... exit(), errno = 32"). It was marked ✗ error and would be re-reduced.

from eqsanscli.integrations.drtsans_runner import ReductionResult
import eqsanscli.services.reduction_service as rs


def _fake_run(stdout, stderr, returncode):
    def _run(json_path, cancel_event=None, drtsans_version="default", progress_cb=None):
        return ReductionResult(
            success=(returncode == 0), json_path=json_path, output_file="",
            elapsed_seconds=1.0, stdout=stdout, stderr=stderr, return_code=returncode,
            log_file="", err_file="",
        )
    return _run


_QT_STDOUT = ("...\nSaveNexus to x_120_processed.nxs\nLinear binning for 0!\n"
              'Cannot install event loop hook for "qt" when running with `--simple-prompt`.\n'
              "NOTE: Tk is supported natively; use Tk apps and Tk backends with `--simple-prompt`.\n")
_ICE_STDERR = "ICE default IO error handler doing an exit(), pid = 350169, errno = 32\n"


def test_gui_teardown_after_complete_reduction_is_success(monkeypatch):
    d = tempfile.mkdtemp()
    row = _row(1, "a20a0", empty_beam="99")
    name = row.output_stem
    # simulate the time-slice output layout drtsans actually wrote
    for slc in (0, 100, 120):
        for frame in (0, 1):
            open(os.path.join(d, f"{name}_{slc}_frame_{frame}_Iq.dat"), "w").close()

    monkeypatch.setattr(rs, "run_reduction", _fake_run(_QT_STDOUT, _ICE_STDERR, 1))
    result = rs.reduce_row(row=row, ipts=38151, user_configs={}, output_dir=d)

    assert result.success is True                 # rescued from the nonzero exit
    assert row.status == "done"                   # so it won't be re-reduced
    assert "non-fatal GUI/display" in result.note
    assert result.output_file.endswith("_Iq.dat") and os.path.exists(result.output_file)


def test_real_crash_with_traceback_stays_failed(monkeypatch):
    d = tempfile.mkdtemp()
    row = _row(1, "a20a0", empty_beam="99")
    name = row.output_stem
    open(os.path.join(d, f"{name}_0_frame_0_Iq.dat"), "w").close()  # partial output exists
    crash = _QT_STDOUT + "Traceback (most recent call last):\n  ...\nValueError: bad\n"

    monkeypatch.setattr(rs, "run_reduction", _fake_run(crash, "", 1))
    result = rs.reduce_row(row=row, ipts=38151, user_configs={}, output_dir=d)

    assert result.success is False                # a genuine crash is not masked
    assert row.status == "error"
    assert not result.note


def test_gui_teardown_but_no_output_stays_failed(monkeypatch):
    d = tempfile.mkdtemp()                        # no I(Q) files written
    row = _row(1, "a20a0", empty_beam="99")
    monkeypatch.setattr(rs, "run_reduction", _fake_run(_QT_STDOUT, _ICE_STDERR, 1))
    result = rs.reduce_row(row=row, ipts=38151, user_configs={}, output_dir=d)
    assert result.success is False                # nothing produced → real failure
    assert row.status == "error"


# --- per-row output directory wins over session-wide + config outputdir ------

def test_reduce_row_uses_per_row_output_override(monkeypatch):
    import json
    sess = tempfile.mkdtemp()
    override = tempfile.mkdtemp()
    row = _row(1, "poly", empty_beam="99")
    row.output_override = override
    # config carries its own outputdir (as /set outputdir would leave it) — the
    # row override must still win.
    cfg = row.configuration
    user_configs = {cfg: {"outputdir": sess}}

    captured = {}
    def _run(json_path, cancel_event=None, drtsans_version="default", progress_cb=None):
        captured["json_path"] = json_path
        captured["outputDir"] = json.load(open(json_path))["configuration"]["outputDir"]
        return ReductionResult(success=True, json_path=json_path, output_file="",
                               elapsed_seconds=1.0, stdout="", stderr="", return_code=0)
    monkeypatch.setattr(rs, "run_reduction", _run)

    rs.reduce_row(row=row, ipts=1, user_configs=user_configs, output_dir=sess)
    assert captured["outputDir"] == override                  # row override wins
    assert captured["json_path"].startswith(override + os.sep)  # JSON written there


def test_reduce_refuses_unwritable_per_row_override(monkeypatch):
    ro = _readonly_dir()
    try:
        state = _state()
        # row 1 is the complete row; point it at a read-only dir
        state.current_table.rows[0].output_override = ro
        result = _run(handle_reduce(["1"], state))
        assert result.success is False
        assert result.data is None
        assert "permission denied" in result.message
    finally:
        os.chmod(ro, 0o700)


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
