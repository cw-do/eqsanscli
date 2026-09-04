"""`/autopilot --to N` — stop after step N.

Reported gap: "run autopilot until you get scalefactor" was interpreted as
`--autopilot --from 1 --till 7`, but no `--till`/`--to` flag existed, so the
whole 13-step pipeline ran to completion. This covers both the parser (the flag,
its aliases, validation, and rejecting an unknown flag instead of eating the
number after it as the IPTS) and the engine (the run stops after the target step
and does not dispatch later-step commands).

    python -m pytest -q tests/test_autopilot_tostep.py
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.commands.autopilot import handle_autopilot
from eqsanscli.commands.router import CommandResult
from eqsanscli.models.session_state import SessionState
from eqsanscli.services.autopilot import _user_param_snapshot, run_autopilot_sync
from eqsanscli.services.matching_service import add_run_class_column, match_runs


def _parse(args):
    st = SessionState()
    st.ipts = 12345  # so "current" resolves
    return asyncio.new_event_loop().run_until_complete(handle_autopilot(args, st))


# --- parser ---------------------------------------------------------------

def test_to_flag_parses():
    r = _parse(["current", "--to", "8"])
    assert r.success and r.data.get("to_step") == 8


def test_till_and_until_are_aliases():
    assert _parse(["current", "--till", "7"]).data.get("to_step") == 7
    assert _parse(["current", "--until", "9"]).data.get("to_step") == 9


def test_to_out_of_range_rejected():
    assert not _parse(["current", "--to", "99"]).success
    assert not _parse(["current", "--to", "0"]).success


def test_to_before_from_rejected():
    assert not _parse(["current", "--from", "9", "--to", "8"]).success


def test_unknown_flag_rejected_not_eaten_as_ipts():
    # The original bug: `--till 7` dropped the flag and parsed 7 as the IPTS,
    # so autopilot ran end to end. An unknown flag must now be an error.
    r = _parse(["current", "--bogus", "7"])
    assert not r.success
    assert "bogus" in r.message.lower()


# --- engine ---------------------------------------------------------------

def _state_with_table(tmpdir):
    """A session ready for --from 5 (catalog + matched table + empty beams)."""
    rows = [
        dict(run_number=500, title="EB 4m 6A", detector_distance=4.0, wavelength=6.0, frequency=60),
        dict(run_number=501, title="T-porsil 4m 6A", detector_distance=4.0, wavelength=6.0, frequency=60),
        dict(run_number=502, title="S-porsil 4m 6A", detector_distance=4.0, wavelength=6.0, frequency=60),
        dict(run_number=503, title="S-widget 4m 6A", detector_distance=4.0, wavelength=6.0, frequency=60),
    ]
    # Mark 500 as the empty beam so matched rows get a beam centre.
    df = add_run_class_column(pd.DataFrame(rows))
    df.loc[df["run_number"] == 500, "run_class"] = "empty_trans"
    st = SessionState()
    st.ipts = 12345
    st.output_directory = tmpdir
    st.catalog = df
    table, _ = match_runs(df, ipts=12345)
    for row in table.rows:
        if not row.empty_beam:
            row.empty_beam = "500"
    st.tables[st.active_table] = table
    table.name = st.active_table
    return st


def _run_to(to_step, from_step=5):
    with tempfile.TemporaryDirectory() as tmp:
        st = _state_with_table(tmp)
        dispatched: list[str] = []
        log: list[str] = []

        def dispatch_sync(cmd: str) -> CommandResult:
            dispatched.append(cmd)
            return CommandResult(success=True, message="", data=None)

        def write(msg: str) -> None:
            log.append(msg)

        run_autopilot_sync(
            ipts=12345, state=st, dispatch_sync=dispatch_sync, write=write,
            from_step=from_step, to_step=to_step,
        )
        return dispatched, "\n".join(log)


def test_stops_after_step_5_before_standard():
    dispatched, log = _run_to(5)
    assert "AUTOPILOT STOPPED (--to 5)" in log
    # Output dir was set (step 5); nothing from steps 6+ ran.
    assert any(c.startswith("/set outputdir") for c in dispatched)
    assert not any("/calibrate" in c for c in dispatched)
    assert not any(c.startswith("/plot") for c in dispatched)
    # The scale block never printed a completion for step 6.
    assert "Step 6/13" not in log or "Reducing" not in log


def test_stop_writes_resume_hint():
    _, log = _run_to(5)
    assert "--from 6" in log  # resume hint = step_completed + 1


def test_full_run_has_no_stop_banner():
    # Without --to, no stop banner; the plot step (13) is reached.
    with tempfile.TemporaryDirectory() as tmp:
        st = _state_with_table(tmp)
        log: list[str] = []
        run_autopilot_sync(
            ipts=12345, state=st,
            dispatch_sync=lambda c: CommandResult(success=True, message="", data=None),
            write=lambda m: log.append(m),
            from_step=5, to_step=None,
        )
    text = "\n".join(log)
    assert "AUTOPILOT STOPPED" not in text
    assert "Step 13/13" in text


# --- --from 2 must build the table, not require one -----------------------

def _catalog_state(ipts=111):
    from eqsanscli.models.working_table import WorkingTableRow  # noqa: F401
    st = SessionState()
    st.ipts = ipts
    st.catalog = add_run_class_column(pd.DataFrame([
        dict(run_number=1, title="S-x 4m 10A", detector_distance=4.0, wavelength=10.0, frequency=60)]))
    return st


def test_from_2_builds_table_without_requiring_one():
    from eqsanscli.models.working_table import WorkingTableRow
    st = _catalog_state()
    dispatched, log = [], []

    def dispatch_sync(cmd):
        dispatched.append(cmd)
        if cmd == "/matchruns":  # step 2 builds the table here
            st.current_table.add_row(WorkingTableRow(
                index=0, scattering_run="1", sample_name="x", empty_beam="2",
                detector_distance=4.0, wavelength=10.0, frequency=60))
        return CommandResult(success=True, message="", data=None)

    run_autopilot_sync(ipts=111, state=st, dispatch_sync=dispatch_sync,
                       write=lambda m: log.append(m), from_step=2, to_step=2)
    text = "\n".join(log)
    assert "requires a populated working table" not in text
    assert "/matchruns" in dispatched          # step 2 actually ran
    assert "Step 2/13" in text


def test_from_2_still_requires_a_catalog():
    st = SessionState()
    st.ipts = 111  # no catalog loaded
    log = []
    run_autopilot_sync(ipts=111, state=st,
                       dispatch_sync=lambda c: CommandResult(success=True, message="", data=None),
                       write=lambda m: log.append(m), from_step=2)
    assert any("requires a loaded catalog" in m for m in log)


def test_from_3_still_requires_populated_table():
    st = _catalog_state()  # catalog present, table empty
    log = []
    run_autopilot_sync(ipts=111, state=st,
                       dispatch_sync=lambda c: CommandResult(success=True, message="", data=None),
                       write=lambda m: log.append(m), from_step=3)
    assert any("requires a populated" in m for m in log)


# --- Step 4b "user-set" snapshot excludes machine-physics params -----------
# (autopilot's log showed dark/flood/flux/offset under "user-set parameters per
#  config" because a prior /matchruns leaves them in state.configurations; they
#  are resolver-owned, not user edits, and Step 4c re-resolves them.)

def test_snapshot_excludes_resolver_owned_params():
    st = SessionState()
    st.configurations["4m10a"] = {
        "darkfilename": "/mp/2026B/dark.nxs",           # resolver-owned
        "sensitivityfilename": "/mp/2026B/sens.nxs",    # resolver-owned
        "numqbins": 9999,                                # genuine /set config edit
    }
    st.instrument_provenance["4m10a"] = {
        "darkfilename": "/mp/2026B/dark.nxs",
        "sensitivityfilename": "/mp/2026B/sens.nxs",
    }
    snap = _user_param_snapshot(st).get("4m10a", {})
    assert "darkfilename" not in snap
    assert "sensitivityfilename" not in snap
    assert snap.get("numqbins") == 9999   # real edit kept


def test_snapshot_keeps_user_override_of_a_resolved_param():
    # A per-experiment sampleoffset override (differs from the resolver's value)
    # is a genuine edit and must survive.
    st = SessionState()
    st.configurations["4m10a"] = {"sampleoffset": 290.0}
    st.instrument_provenance["4m10a"] = {"sampleoffset": 285.0}
    snap = _user_param_snapshot(st).get("4m10a", {})
    assert snap.get("sampleoffset") == 290.0


def test_snapshot_empty_when_only_matchruns_ran():
    # Config holds only resolver-owned values (no user edits) → nothing user-set.
    st = SessionState()
    st.configurations["4m10a"] = {"darkfilename": "/mp/2026B/dark.nxs"}
    st.instrument_provenance["4m10a"] = {"darkfilename": "/mp/2026B/dark.nxs"}
    assert "4m10a" not in _user_param_snapshot(st)


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
