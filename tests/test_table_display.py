"""Long sample names and run titles must wrap, not truncate, in the TUI tables.

Reported: in the reduction (working) table a long sample name showed as
"70.30PBD_0.25…" — Rich's default column overflow ellipsizes plain-text cells.
The run-number columns only appeared to wrap because their cell text carries an
embedded newline (and even they clipped a long no-space title token). The fix
sets overflow="fold" on every free-text column so the full text wraps onto more
lines, matching what the user expects.

    python -m pytest -q tests/test_table_display.py
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.app import EQSANSApp


def _capture(render_method, *args):
    """Call a bound-style render method with a fake log and return the Table."""
    captured = {}

    def _write(table, **kwargs):
        captured["table"] = table

    fake_log = SimpleNamespace(write=_write)
    # The render methods use only `log` and their data arg, never other self
    # attributes, so a bare namespace stands in for `self`.
    render_method(SimpleNamespace(), fake_log, *args)
    return captured["table"]


def _cols(table):
    return {c.header: c for c in table.columns}


def test_working_table_freetext_columns_fold():
    rows = [{
        "Idx": "1", "Sample": "70.30PBD_0.25phr_d16_fs_3mmsa", "Config": "4m2.5a",
        "Scatt": "187242\n[dim]S-70.30PBD_0.25phr_d16 4m 2.5Afs 3mmsa[/dim]",
        "Trans": "187233\n[dim]T-70.30PBD_0.25phr 4m 2.5Afs 3mmsa[/dim]",
        "Thick": "0.1", "Bkg": "—", "BkgTr": "—", "Empty": "500", "Status": "ready",
    }]
    table = _capture(EQSANSApp._render_working_table, rows)
    cols = _cols(table)
    for name in ["Sample", "Config", "Scatt", "Trans", "Bkg", "BkgTr", "Empty"]:
        assert cols[name].overflow == "fold", f"{name} should fold, not ellipsize"


def test_working_table_freetext_columns_have_no_ellipsis():
    rows = [{
        "Idx": "1", "Sample": "s", "Config": "c", "Scatt": "1", "Trans": "2",
        "Thick": "0.1", "Bkg": "—", "BkgTr": "—", "Empty": "—", "Status": "ready",
    }]
    table = _capture(EQSANSApp._render_working_table, rows)
    cols = _cols(table)
    # The fixed-width numeric/status columns (Idx, Thick, Status) keep the default
    # ellipsis — they are short and must not wrap. No free-text column may.
    for name in ["Sample", "Config", "Scatt", "Trans", "Bkg", "BkgTr", "Empty"]:
        assert cols[name].overflow != "ellipsis", name


def test_stitch_table_sample_folds():
    groups = [{
        "sample_name": "a_very_long_sample_name_that_would_be_clipped",
        "configs": ["4m2.5a"], "files": ["x_Iq.dat"], "overlap": "", "target": "",
        "status": "ready",
    }]
    table = _capture(EQSANSApp._render_stitch_table, groups)
    assert _cols(table)["Sample"].overflow == "fold"


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
