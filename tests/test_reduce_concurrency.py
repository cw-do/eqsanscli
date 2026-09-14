"""A second /reduce (or /autopilot) while one is running must be refused.

Reductions run in a background worker thread, so the TUI input stays live and a
second /reduce could be submitted mid-batch. Without a guard that launches a
*concurrent* batch — a second thread pool (up to 2× the worker count of drtsans
processes), a shared cancel event, interleaved output, and — if a row is in both
batches — the same run reduced twice at once, both writing the same files.

`EQSANSApp._reject_if_busy` is the guard checked at both worker launch sites in
`_render_data`. We exercise it directly (constructing the app via __new__ so no
Textual event loop is needed — the guard touches only the flag and the log).

    python -m pytest -q tests/test_reduce_concurrency.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.app import EQSANSApp


class _FakeLog:
    def __init__(self):
        self.msgs: list[str] = []

    def write(self, renderable):
        self.msgs.append(str(renderable))


def _app(job_running: bool) -> EQSANSApp:
    app = EQSANSApp.__new__(EQSANSApp)   # bypass Textual __init__
    app._job_running = job_running
    return app


def test_busy_refuses_and_explains():
    app = _app(True)
    log = _FakeLog()
    assert app._reject_if_busy(log, "reduction") is True     # caller must not launch
    assert len(log.msgs) == 1
    text = log.msgs[0].lower()
    assert "already running" in text
    assert "reduction" in text
    assert "cancel" in text                                  # tells the user how to proceed


def test_idle_allows_and_is_silent():
    app = _app(False)
    log = _FakeLog()
    assert app._reject_if_busy(log, "reduction") is False    # caller proceeds to launch
    assert log.msgs == []                                    # no noise when idle


def test_message_names_the_job_type():
    app = _app(True)
    log = _FakeLog()
    app._reject_if_busy(log, "autopilot")
    assert "autopilot" in log.msgs[0].lower()


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
