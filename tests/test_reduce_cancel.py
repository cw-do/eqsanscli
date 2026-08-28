"""Cancel during a parallel reduction stops the whole batch, not one job.

Reported: clicking Cancel during a multi-core (parallel) reduction only killed
the in-flight jobs; as each worker freed up the executor started the next queued
job, which spawned a fresh drtsans process before noticing the cancel. So one
click did not stop a 15-job batch.

Root cause: reduce_row / run_reduction only checked the cancel event *after*
launching drtsans. The fix makes reduce_row a no-op when the event is already
set, so every queued row returns instantly instead of launching. This is the
deterministic core of it (the executor-loop also drops queued futures on cancel,
but that path is timing-dependent and not unit-tested here).

    python -m pytest -q tests/test_reduce_cancel.py
"""

from __future__ import annotations

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import eqsanscli.services.reduction_service as rs
from eqsanscli.integrations.drtsans_runner import ReductionResult
from eqsanscli.models.working_table import WorkingTableRow


def _row():
    return WorkingTableRow(
        index=1, scattering_run="500", sample_name="widget",
        transmission_run="501", empty_beam="502",
        detector_distance=4.0, wavelength=6.0, frequency=60,
    )


def test_cancelled_before_start_does_not_launch_drtsans(monkeypatch):
    launched = []

    def _boom(*a, **k):
        launched.append(True)
        raise AssertionError("run_reduction must not be called after cancel")

    monkeypatch.setattr(rs, "run_reduction", _boom)

    ev = threading.Event()
    ev.set()  # user already cancelled
    row = _row()
    result = rs.reduce_row(row=row, ipts=1, user_configs={}, cancel_event=ev)

    assert result.cancelled is True
    assert result.success is False
    assert row.status == "cancelled"
    assert not launched  # drtsans was never spawned


def test_not_cancelled_still_runs(monkeypatch, tmp_path):
    calls = []

    def _fake_run(json_path, cancel_event=None, drtsans_version="default"):
        calls.append(json_path)
        return ReductionResult(
            success=True, json_path=json_path, output_file="",
            elapsed_seconds=0.1, stdout="", stderr="", return_code=0,
        )

    monkeypatch.setattr(rs, "run_reduction", _fake_run)

    ev = threading.Event()  # not set
    row = _row()
    result = rs.reduce_row(
        row=row, ipts=1, user_configs={},
        output_dir=str(tmp_path), cancel_event=ev,
    )

    assert result.success is True
    assert row.status == "done"
    assert len(calls) == 1  # the normal path still launches exactly once


def test_none_cancel_event_is_safe(monkeypatch, tmp_path):
    monkeypatch.setattr(rs, "run_reduction", lambda *a, **k: ReductionResult(
        success=True, json_path="", output_file="", elapsed_seconds=0.0,
        stdout="", stderr="", return_code=0,
    ))
    row = _row()
    # cancel_event=None must not raise on the new early-check.
    result = rs.reduce_row(row=row, ipts=1, user_configs={}, output_dir=str(tmp_path))
    assert result.success is True


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
