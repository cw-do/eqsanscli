"""/display <image.png> — open an existing image file in a viewer.

Unlike /plot (which renders data files), /display shows a PNG already on disk
(mask previews, saved plots). A window needs an X display; without one it reports
the resolved path. The viewer subprocess is not launched in these tests.

    python -m pytest -q tests/test_display.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import eqsanscli.commands.data as data
from eqsanscli.models.session_state import SessionState


def _run(args, state):
    return asyncio.new_event_loop().run_until_complete(data.handle_display(args, state))


def _png(tmp_path, name="demo.png"):
    p = tmp_path / name
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 32)
    return p


def test_usage_when_no_args():
    res = _run([], SessionState())
    assert not res.success and "Usage" in res.message


def test_missing_file_errors(tmp_path):
    st = SessionState()
    st.output_directory = str(tmp_path)
    res = _run(["nope.png"], st)
    assert not res.success and "Not found" in res.message


def test_headless_reports_path(monkeypatch, tmp_path):
    monkeypatch.delenv("DISPLAY", raising=False)
    p = _png(tmp_path)
    st = SessionState()
    st.output_directory = str(tmp_path)
    res = _run([str(p)], st)
    assert res.success
    assert "No X display" in res.message and str(p) in res.message


def test_resolves_via_output_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("DISPLAY", raising=False)
    _png(tmp_path, "mask_preview.png")
    st = SessionState()
    st.output_directory = str(tmp_path)
    res = _run(["mask_preview.png"], st)  # bare name, found in output dir
    assert res.success and "mask_preview.png" in res.message


def test_with_display_launches_viewer(monkeypatch, tmp_path):
    monkeypatch.setenv("DISPLAY", ":0")
    called = {}
    monkeypatch.setattr(data, "display_image", lambda paths: called.setdefault("paths", paths))
    p = _png(tmp_path)
    st = SessionState()
    st.output_directory = str(tmp_path)
    res = _run([str(p)], st)
    assert res.success and "Opening" in res.message
    assert called["paths"] == [str(p)]
    assert res.data and res.data["type"] == "image"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
