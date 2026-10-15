"""Headless mode for a driving agent (v0.52.0; sansbook review B5).

Before: progress was free text; `/reduce` could not be cancelled; an exception in
the reduction/autopilot runner ended the process with no reply; and two
processes on one folder both autosaved, the last one to exit winning.

    python -m pytest -q tests/test_headless.py
"""

from __future__ import annotations

import io
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from eqsanscli import headless
from eqsanscli.models.session_state import SessionState
from eqsanscli.models.working_table import WorkingTable, WorkingTableRow


@pytest.fixture(autouse=True)
def _reset_globals():
    yield
    SessionState.READ_ONLY = False
    SessionState.READ_ONLY_REASON = ""
    headless._EVENTS = False
    headless._TERMINATE.clear()
    headless._REDUCING.clear()


def _env(tmp: Path) -> dict:
    env = dict(os.environ, HOME=str(tmp), PYTHONPATH=str(REPO / "src"), PYTHONNOUSERSITE="1")
    env.pop("OPENROUTER_API_KEY", None)
    return env


# The app's own venv: HOME is moved to tmp, which hides user-site packages that
# system python3 relies on.
PY = str(REPO / ".venv" / "bin" / "python") if (REPO / ".venv" / "bin" / "python").exists() else sys.executable


def _start(tmp: Path, *flags: str) -> subprocess.Popen:
    p = subprocess.Popen([PY, "-m", "eqsanscli", "headless", *flags], cwd=tmp,
                         env=_env(tmp), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True)
    return p


def _ready(p: subprocess.Popen) -> dict:
    while True:
        d = json.loads(p.stdout.readline())
        if (d.get("data") or {}).get("type") == "ready":
            return d


def test_events_flag_and_ready_payload(tmp_path):
    out = subprocess.run([PY, "-m", "eqsanscli", "headless", "--events"], cwd=tmp_path,
                         env=_env(tmp_path), input="/version\n/exit\n", text=True,
                         capture_output=True, timeout=120).stdout
    replies = [json.loads(line) for line in out.splitlines()]
    ready = next(r for r in replies if (r["data"] or {}).get("type") == "ready")
    assert ready["data"] == {"type": "ready", "read_only": False, "events": True}
    assert any((r["data"] or {}).get("type") == "version" for r in replies)


def test_second_process_on_the_folder_is_read_only(tmp_path):
    a = _start(tmp_path)
    try:
        assert _ready(a)["data"]["read_only"] is False
        b = _start(tmp_path)
        try:
            rb = _ready(b)
            assert rb["data"]["read_only"] is True and "Another eqsanscli" in rb["message"]
            b.stdin.write("/reduce all\n"); b.stdin.flush()
            reply = json.loads(b.stdout.readline())
            assert not reply["success"] and "Read-only" in reply["message"]
        finally:
            b.kill(); b.wait()
    finally:
        a.kill(); a.wait()


def test_sigterm_while_idle_saves_and_replies(tmp_path):
    p = _start(tmp_path)
    try:
        _ready(p)
        p.send_signal(signal.SIGTERM)
        out, _ = p.communicate(timeout=30)
        assert "Session saved" in out
    finally:
        if p.poll() is None:
            p.kill()


def _session_with_a_row(tmp: Path) -> None:
    st = SessionState()
    t = WorkingTable("default")
    t.rows = [WorkingTableRow(index=1, scattering_run="20", sample_name="s", empty_beam="1",
                              transmission_run="21", detector_distance=4, wavelength=2.5, frequency=60)]
    st.tables = {"default": t}; st.active_table = "default"
    st.output_directory = str(tmp / "out")
    st.save(SessionState.auto_save_path())


def _run_inprocess(tmp: Path, monkeypatch, capsys, stdin: str, *argv: str) -> list[dict]:
    monkeypatch.chdir(tmp)                     # before any save: autosave paths are cwd-relative
    monkeypatch.setenv("HOME", str(tmp))
    _session_with_a_row(tmp)
    monkeypatch.setattr(sys, "stdin", io.StringIO(stdin))
    monkeypatch.setattr(signal, "signal", lambda *a, **k: None)   # not the test runner's handler
    headless.run_headless(list(argv))
    return [json.loads(line) for line in capsys.readouterr().out.splitlines()]


def test_runner_exception_still_gets_one_reply(tmp_path, monkeypatch, capsys):
    def boom(*a, **k):
        raise RuntimeError("drtsans exploded")
    monkeypatch.setattr(headless, "_run_reduction_sync", boom)
    replies = _run_inprocess(tmp_path, monkeypatch, capsys, "/reduce all\n/version\n")
    err = [r for r in replies if "drtsans exploded" in r["message"]]
    assert len(err) == 1 and not err[0]["success"]
    assert replies[-1]["data"]["type"] == "version"              # the process kept going


def test_sigterm_during_reduce_cancels_and_exits(tmp_path, monkeypatch, capsys):
    from eqsanscli.integrations.drtsans_runner import ReductionResult
    import eqsanscli.services.reduction_service as rs
    def fake_reduce(row, **kw):
        headless._TERMINATE.set()                                  # SIGTERM arrives mid-row
        row.status = "cancelled"
        r = ReductionResult(success=False, json_path="", output_file="", elapsed_seconds=0.1,
                            stdout="", stderr="", return_code=-15)
        r.cancelled = True
        return r
    monkeypatch.setattr(rs, "reduce_row", fake_reduce)
    replies = _run_inprocess(tmp_path, monkeypatch, capsys, "/reduce all\n/version\n")
    red = next(r for r in replies if (r["data"] or {}).get("type") == "reduction_complete")
    assert red["data"]["cancelled"] and red["data"]["ok"] is False
    assert red["data"]["results"][0]["status"] == "cancelled"
    assert "Terminated" in replies[-1]["message"]                  # /version never ran
