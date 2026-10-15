"""/plot never uploads by itself (v0.47.6).

With DISPLAY unset, /plot used to save the PNG and then upload it to here.now —
a public 24 h link — without being asked: every headless run, SSH session and
autopilot plot step. Uploading is now only an explicit /share.

    python -m pytest -q tests/test_plot_share.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pytest

pytest.importorskip("matplotlib")

from eqsanscli.commands.data import handle_plot
from eqsanscli.models.session_state import SessionState
from eqsanscli.services import share_service


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


def test_plot_without_display_saves_and_does_not_upload(tmp_path, monkeypatch):
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.chdir(tmp_path)

    def no_upload(*a, **k):
        raise AssertionError("/plot must not upload")
    monkeypatch.setattr(share_service, "share_files", no_upload)

    iq = tmp_path / "s1_4m10a_Iq.dat"
    iq.write_text("#Q (1/A)\tI (1/cm)\tdI (1/cm)\n" + "".join(
        f"{0.01 * k:.6E}\t{1.0 / k:.6E}\t{0.01:.6E}\n" for k in range(1, 30)))
    st = SessionState()
    st.output_directory = str(tmp_path)

    res = _run(handle_plot([str(iq)], st))
    assert res.success, res.message
    assert list(tmp_path.glob("*.png")), "PNG should still be written"
    assert "Shared" not in res.message and "/share" in res.message


def test_share_says_the_link_is_public(tmp_path, monkeypatch):
    from eqsanscli.commands import share as share_cmd
    f = tmp_path / "x.png"
    f.write_bytes(b"png")
    monkeypatch.setattr(share_service, "share_files",
                        lambda paths: (True, "https://example.here.now/", ""))
    st = SessionState()
    st.output_directory = str(tmp_path)
    res = _run(share_cmd.handle_share([str(f)], st))
    assert res.success and "PUBLIC" in res.message
