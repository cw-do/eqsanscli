"""rheo-SANS matching: shear rate and shear plane (IPTS-37681, 2026-09-29).

CTAB in a Couette cell, measured in two shear planes (1,3 and 2,3) at several
shear rates, in two configurations. Titles (real, abridged):

    T-empty beam 1,3 4m2.5a         T-empty beam 2,3 4m2.5a
    T-EmptyCupBob 1,3_0shear 4m2.5a  S-EmptyCupBob 1,3_0shear 4m2.5a  (and 2,3)
    T-CTAB 1,3_0shear 4m2.5a        T-CTAB 2,3_0shear 4m2.5a
    S-CTAB 1,3_0.1shear 4m2.5a …    S-CTAB 2,3_0shear-return 4m2.5a

The transmission is measured once, at rest, per plane and serves every shear
rate (TBL-09); 20 rows came out with no transmission. Each plane is a different
beam path, with its own empty beam and empty cup, but every row got the first
of each (CAT-09).

    python -m pytest -q tests/test_rheo_matching.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.services.matching_service import (
    _match_base,
    add_run_class_column,
    match_runs,
)

_TITLES = [
    "T-empty beam 1,3 4m2.5a",            # 100
    "T-EmptyCupBob 1,3_0shear 4m2.5a",    # 101
    "T-EmptyCupBob 2,3_0shear 4m2.5a",    # 102
    "S-EmptyCupBob 1,3_0shear 4m2.5a",    # 103
    "S-EmptyCupBob 2,3_0shear 4m2.5a",    # 104
    "T-empty beam 2,3 4m2.5a",            # 105  measured after the cups
    "T-CTAB 1,3_0shear 4m2.5a",           # 106
    "T-CTAB 2,3_0shear 4m2.5a",           # 107
    "S-CTAB 1,3_0shear 4m2.5a",           # 108
    "S-CTAB 2,3_0.1shear 4m2.5a",         # 109
    "S-CTAB 1,3_1000shear 4m2.5a",        # 110
    "S-CTAB 2,3_0shear-return 4m2.5a",    # 111
]


def _cat():
    return add_run_class_column(pd.DataFrame([
        dict(run_number=100 + i, title=t, detector_distance=4.0, wavelength=2.5,
             frequency=60)
        for i, t in enumerate(_TITLES)
    ]))


def _rows(table):
    return {r.scattering_run: r for r in table.rows}


def test_shear_rate_is_a_condition_token():
    assert _match_base("CTAB_1,3_0.1shear_4m2.5a") == _match_base("CTAB_1,3_0shear_4m2.5a")
    assert _match_base("CTAB_2,3_0shear-return") == _match_base("CTAB_2,3_0shear")
    assert _match_base("CTAB_1,3_1000shear") != _match_base("CTAB_2,3_0shear")
    assert _match_base("shearthin_polymer") == "shearthin_polymer"   # not a rate token


def test_every_shear_rate_gets_its_planes_transmission():
    table, _ = match_runs(_cat())
    rows = _rows(table)
    assert rows["108"].transmission_run == "106"
    assert rows["110"].transmission_run == "106"      # 1000shear → 1,3 at rest
    assert rows["109"].transmission_run == "107"      # 0.1shear, plane 2,3
    assert rows["111"].transmission_run == "107"      # 0shear-return


def test_empty_beam_and_background_follow_the_plane():
    table, warnings = match_runs(_cat())
    rows = _rows(table)
    for run in ("103", "108", "110"):                  # plane 1,3
        assert rows[run].empty_beam == "100"
    for run in ("104", "109", "111"):                  # plane 2,3
        assert rows[run].empty_beam == "105"
    assert (rows["110"].background_scatt, rows["110"].background_trans) == ("103", "101")
    assert (rows["109"].background_scatt, rows["109"].background_trans) == ("104", "102")
    # Every row was decided by its token: no "Using … as default" warning.
    assert not any("as default" in w for w in warnings)
    assert any("chosen per row" in w for w in warnings)


def test_no_title_tokens_restores_first_found():
    table, warnings = match_runs(_cat(), title_tokens=False)
    rows = _rows(table)
    assert rows["109"].empty_beam == "100"
    assert rows["109"].background_scatt == "103"
    assert any("as default" in w for w in warnings)


def test_titles_without_distinguishing_tokens_unchanged():
    cat = add_run_class_column(pd.DataFrame([
        dict(run_number=200 + i, title=t, detector_distance=4.0, wavelength=10.0,
             frequency=60)
        for i, t in enumerate([
            "T-empty 4m 10a", "T-empty beam 4m 10a",
            "S-banjo 4m 10a", "S-emptycell 4m 10a",
            "T-sampleA 4m 10a", "S-sampleA 4m 10a",
        ])
    ]))
    table, warnings = match_runs(cat)
    row = _rows(table)["205"]
    assert row.empty_beam == "200"
    assert row.background_scatt == "202"
    assert any("empty beam runs found" in w for w in warnings)
    assert any("background scatt runs found" in w for w in warnings)


# --- compact configuration in the title (v0.47.2) ---------------------------
# "4m2.5a" written without a space stayed in the sample name, so the output
# doubled it (CTAB_1,3_0shear_4m2.5a_4m2.5a_Iq.dat) and every sample became one
# stitch group per configuration: autopilot said "No stitchable groups found".

from eqsanscli.models.working_table import WorkingTable, WorkingTableRow
from eqsanscli.services.matching_service import _extract_sample_name, strip_config_tokens
from eqsanscli.services.merge_service import build_stitch_table


def test_compact_configuration_leaves_the_sample_name():
    assert _extract_sample_name("S-CTAB 1,3_0.1shear 4m2.5a") == "CTAB_1,3_0.1shear"
    assert _extract_sample_name("T-empty beam 2,3 8m8a") == "empty_beam_2,3"
    assert _extract_sample_name("S-x_0shear_2p5m2p5a_wait") == "x_0shear_wait"
    assert _extract_sample_name("S-poly 4m2.5a30hz") == "poly"
    # a name that only contains such letters is not a configuration word
    assert _extract_sample_name("S-sample2m5a 4m 10a") == "sample2m5a"
    # spaced form unchanged
    assert _extract_sample_name("S-abc 4m 10A") == "abc"


def test_rows_named_before_the_fix_still_stitch(tmp_path):
    table = WorkingTable(name="t")
    for cfg, dist, wl in (("4m2.5a", 4.0, 2.5), ("8m10a", 8.0, 10.0)):
        row = WorkingTableRow(index=0, scattering_run="1", sample_name=f"CTAB_1,3_0shear_{cfg}",
                              detector_distance=dist, wavelength=wl, frequency=60)
        table.add_row(row)
        (tmp_path / f"{row.output_stem}_Iq.dat").write_text("0.01 1.0 0.1\n")
    assert strip_config_tokens("CTAB_1,3_0shear_8m10a") == "CTAB_1,3_0shear"
    groups = build_stitch_table(table, str(tmp_path))
    assert len(groups) == 1
    assert groups[0].sample_name == "CTAB_1,3_0shear"
    assert groups[0].status != "1 config"
