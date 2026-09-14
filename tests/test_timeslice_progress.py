"""Time-slice reduction: up-front slice estimate + live progress heartbeat.

A user reducing a 1-hour run at a 5 s interval (720 slices) had no idea how many
slices that implied, and the run showed no progress because drtsans output was
captured only at the end. These cover the two pieces added in response:

  - `timeslice_estimate` — how many slices a config/duration implies (None off).
  - `make_slice_progress` — a throttled callback that counts drtsans's per-slice
    `SaveNexus to …_processed.nxs` lines and emits a readable heartbeat.
  - `SessionState.run_duration` — the duration lookup the estimate needs.

    python -m pytest -q tests/test_timeslice_progress.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.models.session_state import SessionState
from eqsanscli.services.reduction_service import make_slice_progress, timeslice_estimate


# --- estimate --------------------------------------------------------------

def test_estimate_counts_slices_and_rounds_up():
    est = timeslice_estimate({"usetimeslice": True, "timesliceinterval": 5}, 3600)
    assert est == {"slices": 720, "interval_s": 5.0, "duration_s": 3600}
    # a partial final slice rounds up
    assert timeslice_estimate({"usetimeslice": True, "timesliceinterval": 7}, 100)["slices"] == 15


def test_estimate_none_when_not_slicing_or_unknown():
    assert timeslice_estimate({"usetimeslice": False, "timesliceinterval": 5}, 3600) is None
    assert timeslice_estimate({"usetimeslice": True, "timesliceinterval": 0}, 3600) is None
    assert timeslice_estimate({"usetimeslice": True, "timesliceinterval": 5}, 0) is None


# --- progress callback -----------------------------------------------------

def test_progress_counts_savenexus_and_formats_fraction():
    got = []
    cb = make_slice_progress(got.append, label="poly", total=4, every=1, min_seconds=0)
    for i in range(4):
        cb(f"SaveNexus to /x/poly_{i}_processed.nxs\n")
    cb("[INFO] Split frame for DataType.IQ_MOD\n")   # not a slice marker → ignored
    assert len(got) == 4
    assert "poly: slice 1/4 (25%)" in got[0]
    assert "slice 4/4 (100%)" in got[3]


def test_progress_throttles_by_count():
    got = []
    cb = make_slice_progress(got.append, total=100, every=25, min_seconds=1e9)
    for i in range(100):
        cb(f"SaveNexus to /x/s_{i}_processed.nxs\n")
    # first fires immediately, then every 25th → 1, 26, 51, 76 = 4 lines
    assert len(got) == 4


def test_progress_pct_never_exceeds_100():
    got = []
    cb = make_slice_progress(got.append, total=2, every=1, min_seconds=0)
    for i in range(5):                               # more slices than estimated
        cb(f"SaveNexus to /x/s_{i}_processed.nxs\n")
    assert "(100%)" in got[-1] and "101%" not in got[-1]


# --- duration lookup -------------------------------------------------------

def test_run_duration_from_catalog():
    state = SessionState()
    state.catalog = pd.DataFrame([
        {"run_number": 188000, "title": "S-poly", "duration": 3600},
        {"run_number": 188001, "title": "T-poly", "duration": 120},
    ])
    assert state.run_duration("188000") == 3600
    assert state.run_duration("188001, 188002") == 120   # comma → first
    assert state.run_duration("999999") == 0             # unknown
    assert state.run_duration("") == 0


if __name__ == "__main__":
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001
            print(f"  FAIL  {name}: {exc}")
            failures.append(name)
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed"
          + (f" — FAILED: {', '.join(failures)}" if failures else ""))
    sys.exit(1 if failures else 0)
