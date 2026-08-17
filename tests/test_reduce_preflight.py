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
            output_file, log_file, err_file = "out.dat", "", ""
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
