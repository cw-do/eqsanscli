"""/reclass --sample respects the S-/T- prefix.

Field report (2026-09-29): "S-emptycupbob are background scattering and
T-emptycupbob are background transmission" became
    /reclass --sample EmptyCupBob bkg       → all 10 runs BkgS
    /reclass --sample EmptyCupBob bkgtrans  → all 10 runs BkgT
because the name match discarded the prefix, so neither command could address
one half. It also revived two runs the user had set to ignore (N → BkgS).

    python -m pytest -q tests/test_reclass.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.commands.catalog import _match_catalog_title, handle_reclass
from eqsanscli.models.session_state import SessionState

# The report's runs: 188901/188902 were set aside (N) by the user.
_RUNS = [
    (188901, "T-EmptyCupBob 1,3_0shear 4m2.5a", "ignore"),
    (188902, "T-EmptyCupBob 2,3_0shear 4m2.5a", "ignore"),
    (188904, "T-EmptyCupBob 1,3_0shear 4m2.5a", "bkg_scatt"),
    (188905, "T-EmptyCupBob 2,3_0shear 4m2.5a", "bkg_scatt"),
    (188906, "T-EmptyCupBob 1,3_0shear 8m10a", "bkg_scatt"),
    (188908, "S-EmptyCupBob 1,3_0shear 4m2.5a", "bkg_scatt"),
    (188910, "S-EmptyCupBob 1,3_0shear 8m10a", "bkg_scatt"),
    (188920, "S-CupSample 8m10a", "scattering"),
]


def _state() -> SessionState:
    s = SessionState()
    s.catalog_data = [
        {"run_number": rn, "title": t, "run_class": c} for rn, t, c in _RUNS
    ]
    return s


def _classes(s: SessionState) -> dict[int, str]:
    return {r["run_number"]: r["run_class"] for r in s.catalog_data}


def _reclass(s: SessionState, *args: str):
    return asyncio.get_event_loop().run_until_complete(handle_reclass(list(args), s))


def test_prefixed_name_matches_only_that_prefix():
    assert _match_catalog_title("S-EmptyCupBob", "S-EmptyCupBob 1,3_0shear 4m2.5a")
    assert not _match_catalog_title("S-EmptyCupBob", "T-EmptyCupBob 1,3_0shear 4m2.5a")
    assert _match_catalog_title("t-emptycupbob", "T-EmptyCupBob 1,3_0shear 4m2.5a")
    assert _match_catalog_title("T-*cup*", "T-EmptyCupBob 8m10a")
    # Unprefixed name still matches both halves, as before.
    assert _match_catalog_title("EmptyCupBob", "S-EmptyCupBob 8m10a")
    assert _match_catalog_title("EmptyCupBob", "T-EmptyCupBob 8m10a")


def test_the_reported_sentence_now_splits_correctly():
    s = _state()
    assert _reclass(s, "--sample", "S-EmptyCupBob", "bkg").success
    assert _reclass(s, "--sample", "T-EmptyCupBob", "bkgtrans").success
    c = _classes(s)
    assert c[188908] == c[188910] == "bkg_scatt"
    assert c[188904] == c[188905] == c[188906] == "bkg_trans"
    assert c[188901] == c[188902] == "ignore"      # not revived
    assert c[188920] == "scattering"                # other sample untouched


def test_background_class_follows_the_prefix():
    s = _state()
    r = _reclass(s, "--sample", "EmptyCupBob", "background")
    assert r.success
    c = _classes(s)
    assert c[188908] == c[188910] == "bkg_scatt"
    assert c[188904] == c[188905] == c[188906] == "bkg_trans"


def test_name_match_leaves_ignored_runs_and_says_so():
    s = _state()
    r = _reclass(s, "--sample", "EmptyCupBob", "background")
    assert _classes(s)[188901] == "ignore"
    assert "188901" in r.message and "ignored" in r.message
    # Naming the run explicitly still revives it.
    assert _reclass(s, "188901", "bkgtrans").success
    assert _classes(s)[188901] == "bkg_trans"


def test_literal_class_against_the_prefix_warns():
    s = _state()
    r = _reclass(s, "--sample", "EmptyCupBob", "bkg")
    assert r.success
    assert _classes(s)[188904] == "bkg_scatt"       # literal class still applied
    assert "disagree" in r.message and "background" in r.message


def test_ignore_by_name_still_reaches_everything():
    s = _state()
    assert _reclass(s, "--sample", "EmptyCupBob", "i").success
    assert all(c == "ignore" for rn, c in _classes(s).items() if rn != 188920)
