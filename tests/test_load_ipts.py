"""/load ipts with no number infers the IPTS from the current folder.

Requested: running eqsanscli from /SNS/EQSANS/IPTS-39659/shared/ and typing
`/load ipts` (no number) should load 39659.

    python -m pytest -q tests/test_load_ipts.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import eqsanscli.commands.catalog as cat
from eqsanscli.models.session_state import SessionState


def _run(args, state):
    return asyncio.new_event_loop().run_until_complete(cat.handle_load_ipts(args, state))


def test_ipts_from_cwd_variants(monkeypatch):
    for path, want in [
        ("/SNS/EQSANS/IPTS-39659/shared", 39659),
        ("/SNS/EQSANS/IPTS-39659", 39659),           # no trailing slash
        ("/SNS/EQSANS/IPTS-39659/shared/output", 39659),
        ("/home/user/elsewhere", None),
    ]:
        monkeypatch.setattr(cat.os, "getcwd", lambda p=path: p)
        assert cat._ipts_from_cwd() == want


def _stub_fetch(monkeypatch):
    monkeypatch.setattr(cat._catalog_service, "fetch",
                        lambda ipts: pd.DataFrame([dict(run_number=1, title="S-x 4m 10A")]))
    monkeypatch.setattr(cat, "_build_catalog_rows", lambda df: [])


def test_load_no_arg_infers_from_cwd(monkeypatch):
    _stub_fetch(monkeypatch)
    monkeypatch.setattr(cat.os, "getcwd", lambda: "/SNS/EQSANS/IPTS-39659/shared")
    st = SessionState()
    res = _run([], st)
    assert res.success and res.data["ipts"] == 39659
    assert st.ipts == 39659
    assert "inferred" in res.message


def test_load_no_arg_outside_ipts_folder_shows_usage(monkeypatch):
    monkeypatch.setattr(cat.os, "getcwd", lambda: "/home/user/elsewhere")
    res = _run([], SessionState())
    assert not res.success and "Usage" in res.message


def test_explicit_number_still_works(monkeypatch):
    _stub_fetch(monkeypatch)
    monkeypatch.setattr(cat.os, "getcwd", lambda: "/home/user/elsewhere")
    res = _run(["38659"], SessionState())
    assert res.success and res.data["ipts"] == 38659
    assert "inferred" not in res.message


def test_invalid_number_rejected():
    res = _run(["notanumber"], SessionState())
    assert not res.success and "Invalid" in res.message


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
