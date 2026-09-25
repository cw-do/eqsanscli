"""Title tokens written by a proposal-driven script generator (v0.45.0).

A proposal says which background each sample uses; the acquisition script can
write that into the titles, with the cell thickness:

    S-bkg2_D2O40_th1mm 4m 10a 25C          background number 2
    S-SiPEG_D2O40_bg2_th1mm 4m 10a 25C     "my background is bkg2, 1 mm cell"

Before this, /matchruns gave every sample the lowest-numbered background of its
configuration and left thickness at 0.1 cm, so a contrast series or a
temperature series with its own solvent runs was paired wrongly. Protocol
BKG-04 and TBL-08. Titles without the tokens must match exactly as before.

    python -m pytest -q tests/test_title_tokens.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.commands.matching import handle_matchruns
from eqsanscli.models.session_state import SessionState
from eqsanscli.services.matching_service import (
    add_run_class_column,
    background_pointer,
    classify_title,
    match_runs,
    merge_new_runs,
    title_thickness_cm,
)


def _cat(titles, start=100, dist=4.0, wl=10.0):
    return add_run_class_column(pd.DataFrame([
        dict(run_number=start + i, title=t, detector_distance=dist, wavelength=wl, frequency=60)
        for i, t in enumerate(titles)
    ]))


CONTRAST = [
    "T-empty 4m 10a",
    "T-bkg1_D2O0_th1mm 4m 10a", "T-bkg2_D2O100_th2mm 4m 10a",
    "T-Si_D2O0_bg1_th1mm 4m 10a", "T-Si_D2O100_bg2_th2mm 4m 10a",
    "S-bkg1_D2O0_th1mm 4m 10a", "S-bkg2_D2O100_th2mm 4m 10a",
    "S-Si_D2O0_bg1_th1mm 4m 10a", "S-Si_D2O100_bg2_th2mm 4m 10a",
]


def _row(table, name):
    return next(r for r in table.rows if r.sample_name == name)


def test_token_parsing():
    assert background_pointer("Si_D2O40_bg2_th1mm") == 2
    assert background_pointer("bg12") == 12
    assert background_pointer("sbg2") is None           # not a word of its own
    assert background_pointer("Si_bg2x") is None
    assert title_thickness_cm("Si_th2mm") == 0.2
    assert title_thickness_cm("Si_th0p5mm_25C") == 0.05
    assert title_thickness_cm("Si_th2cm") is None       # mm only, by design
    assert title_thickness_cm("width2mm") is None


def test_the_pointer_must_not_be_spelled_bkg():
    """Any title containing "bkg" is a background — the reason the sample-side
    pointer is bg<N>."""
    assert classify_title("S-Si_D2O40_B_bkg2 4m 10a") == "bkg_scatt"
    assert classify_title("S-Si_D2O40_bg2_th1mm 4m 10a") == "scattering"


def test_each_sample_gets_the_background_its_title_names():
    table, warnings = match_runs(_cat(CONTRAST))
    s0, s100 = _row(table, "Si_D2O0_bg1_th1mm"), _row(table, "Si_D2O100_bg2_th2mm")
    assert (s0.background_scatt, s0.background_trans) == ("105", "101")
    assert (s100.background_scatt, s100.background_trans) == ("106", "102")
    assert s0.transmission_run == "103" and s100.transmission_run == "104"
    # the "several backgrounds, using the first" warning is moot when every sample names one
    assert not any("background scatt runs found" in w for w in warnings)


def test_thickness_comes_from_the_title_for_every_row():
    table, _ = match_runs(_cat(CONTRAST))
    assert _row(table, "Si_D2O0_bg1_th1mm").thickness == 0.1
    assert _row(table, "Si_D2O100_bg2_th2mm").thickness == 0.2
    assert _row(table, "bkg2_D2O100_th2mm").thickness == 0.2
    assert _row(table, "bkg1_D2O0_th1mm").background_scatt == ""     # EMP-03 unchanged


def test_temperature_series_uses_the_background_at_the_same_temperature():
    titles = ["T-empty 4m 10a"]
    for t in (20, 40):
        titles += [f"T-bkg1_D2O_th1mm 4m 10a {t}C", f"T-C12E5_D2O_bg1_th1mm 4m 10a {t}C",
                   f"S-bkg1_D2O_th1mm 4m 10a {t}C", f"S-C12E5_D2O_bg1_th1mm 4m 10a {t}C"]
    table, _ = match_runs(_cat(titles))
    s20, s40 = _row(table, "C12E5_D2O_bg1_th1mm_20C"), _row(table, "C12E5_D2O_bg1_th1mm_40C")
    assert s20.background_scatt == "103" and s20.background_trans == "101"
    assert s40.background_scatt == "107" and s40.background_trans == "105"


def test_a_single_background_serves_every_temperature():
    titles = ["T-empty 4m 10a", "T-bkg1_D2O_th1mm 4m 10a", "S-bkg1_D2O_th1mm 4m 10a",
              "T-x_bg1 4m 10a 20C", "S-x_bg1 4m 10a 20C", "T-x_bg1 4m 10a 40C", "S-x_bg1 4m 10a 40C"]
    table, warnings = match_runs(_cat(titles))
    assert {r.background_scatt for r in table.rows if r.sample_name.startswith("x_")} == {"102"}
    assert not warnings


def test_an_unresolvable_pointer_keeps_the_default_and_says_so():
    titles = ["T-empty 4m 10a", "S-bkg1_D2O 4m 10a", "T-bkg1_D2O 4m 10a",
              "S-x_bg3 4m 10a", "T-x_bg3 4m 10a"]
    table, warnings = match_runs(_cat(titles))
    assert _row(table, "x_bg3").background_scatt == "101"            # the pre-0.45 default
    assert any("asks for bkg3" in w and "no bkg3 run" in w for w in warnings)


def test_no_title_tokens_restores_the_old_behaviour():
    table, warnings = match_runs(_cat(CONTRAST), title_tokens=False)
    assert {r.background_scatt for r in table.rows if r.sample_name.startswith("Si_")} == {"105"}
    assert all(r.thickness == 0.1 for r in table.rows)
    assert any("background scatt runs found" in w for w in warnings)


def test_titles_without_tokens_match_exactly_as_before():
    legacy = ["T-empty 4m 10A", "T-banjo_D2O 4m 10A", "S-banjo_D2O 4m 10A", "T-banjo_H2O 4m 10A",
              "S-banjo_H2O 4m 10A", "T-lyso 4m 10A", "S-lyso 4m 10A", "S-lyso 40C 4m 10A",
              "S-poly_1.5 4m 10A 0.2C"]
    on, w_on = match_runs(_cat(legacy))
    off, w_off = match_runs(_cat(legacy), title_tokens=False)
    assert [r.to_dict() for r in on.rows] == [r.to_dict() for r in off.rows]
    assert w_on == w_off


def test_update_does_not_overwrite_a_title_named_background():
    """--update copies the config's background onto new rows; a row whose title
    names its background must keep that one."""
    first = CONTRAST[:3] + CONTRAST[5:7] + ["T-Si_D2O0_bg1_th1mm 4m 10a", "S-Si_D2O0_bg1_th1mm 4m 10a"]
    table, _ = match_runs(_cat(first))
    fresh = _cat(first + ["T-Si_D2O100_bg2_th2mm 4m 10a", "S-Si_D2O100_bg2_th2mm 4m 10a"])
    merged, _, n_new, _ = merge_new_runs(table, fresh)
    assert n_new == 1
    new = _row(merged, "Si_D2O100_bg2_th2mm")
    assert new.background_scatt == "104" and new.background_trans == "102"
    assert new.thickness == 0.2


def test_matchruns_command_flag_and_summary():
    state = SessionState()
    state.catalog = _cat(CONTRAST)
    res = asyncio.run(handle_matchruns([], state))
    assert res.success and "From title tokens" in res.message
    assert _row(state.current_table, "Si_D2O100_bg2_th2mm").background_scatt == "106"
    res = asyncio.run(handle_matchruns(["--no-title-tokens"], state))
    assert res.success and "From title tokens" not in res.message
    assert _row(state.current_table, "Si_D2O100_bg2_th2mm").background_scatt == "105"
