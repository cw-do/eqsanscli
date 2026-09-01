"""Fill a user's own reduction script from the working table (`/export script --like`).

The fixture (tests/fixtures/example_reduction_script.py) is a real 4-config,
per-sample-loop EQSANS script with inline stitching. The contract: fill the input
arrays (scattering/transmission/background/empty-beam run lists, sample names,
thickness) from the table and keep EVERY other line byte-for-byte.

    python -m pytest -q tests/test_script_templating.py
"""

from __future__ import annotations

import ast
import asyncio
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.commands.export import handle_export_script
from eqsanscli.models.session_state import SessionState
from eqsanscli.models.working_table import WorkingTable, WorkingTableRow
from eqsanscli.services import script_templating as st

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "example_reduction_script.py"
EXAMPLE = FIXTURE.read_text()

# The fixture's four config blocks, in order.
CONFIGS = [(9, 15, 60), (4, 10, 60), (2.5, 2.5, 60), (1.3, 1, 60)]


def _table(nsamples=6, configs=CONFIGS, base=190000, names=None):
    names = names or [f"P{i+1}" for i in range(nsamples)]
    t = WorkingTable(name="default")
    for ci, (d, w, f) in enumerate(configs):
        for si, nm in enumerate(names):
            t.add_row(WorkingTableRow(
                index=0, scattering_run=str(base + ci * 100 + si), sample_name=nm,
                transmission_run=str(base + ci * 100 + 50 + si),
                background_scatt=str(base + ci * 100 + 80),
                background_trans=str(base + ci * 100 + 81),
                empty_beam=str(base + ci * 100 + 90),
                detector_distance=d, wavelength=w, frequency=f, thickness=2.0))
    return t


# --- extraction / parse / identify / align -------------------------------

def test_extract_groups_by_physical_config():
    data = st.extract_table_data(_table())
    assert set(data) == {"9m15a", "4m10a", "2.5m2.5a", "1.3m1a"}
    assert data["9m15a"].order == [f"P{i+1}" for i in range(6)]


def test_identify_finds_roles_and_hints():
    m = st.identify(st.parse_example(EXAMPLE))
    assert m.sample_names is not None and m.sample_thick is not None
    assert sorted(m.role_blocks) == ["bkgscatt", "bkgtrans", "emptybeam", "samscatt", "samtrans"]
    assert all(sorted(m.role_blocks[r]) == [0, 1, 2, 3] for r in m.role_blocks)
    assert m.config_hint == {0: "9m15a", 1: "4m10a", 2: "2.5m2.5a", 3: "1.3m1a"}


def test_align_matches_hints_to_table():
    m = st.identify(st.parse_example(EXAMPLE))
    al = st.align(m, st.extract_table_data(_table()))
    assert al.index_to_config == {0: "9m15a", 1: "4m10a", 2: "2.5m2.5a", 3: "1.3m1a"}
    assert al.reference_order == [f"P{i+1}" for i in range(6)]
    assert al.warnings == []


# Hint-less template: blocks must be filled LOW-Q first, regardless of the table's
# own (distance-ascending) order — the stitch assumes block 0/iq0 is the low-Q data.
HINTLESS_2BLOCK = """\
ipts_number = 1
output_directory = "/x/"
sample_names = ['A']
sample_thick = [1]
samscatt_1 = [1]
samtrans_1 = [2]
bkgscatt_1 = [3]
bkgtrans_1 = [4]
emptybeam_1 = 5
samscatt_2 = [6]
samtrans_2 = [7]
bkgscatt_2 = [8]
bkgtrans_2 = [9]
emptybeam_2 = 10
# BELOW IS REDUCTION CODE
for i in range(len(sample_names)):
    pass
"""


def _table_reversed_order():
    """Two configs added 2.5m first (as /matchruns sorts by distance ascending)."""
    t = WorkingTable(name="default")
    for d, w in [(2.5, 2.5), (4, 10)]:
        t.add_row(WorkingTableRow(
            index=0, scattering_run="900", sample_name="A", transmission_run="901",
            background_scatt="902", background_trans="903", empty_beam="904",
            detector_distance=d, wavelength=w, frequency=60, thickness=1.0))
    return t


def test_hintless_blocks_align_low_q_first():
    data = st.extract_table_data(_table_reversed_order())
    assert list(data) == ["2.5m2.5a", "4m10a"]  # table order is 2.5m first
    m = st.identify(st.parse_example(HINTLESS_2BLOCK))
    al = st.align(m, data)
    # block 1 (iq1, low-Q) must be 4m10a; block 2 (high-Q) must be 2.5m2.5a
    assert al.index_to_config == {1: "4m10a", 2: "2.5m2.5a"}


def test_hintless_fill_is_monotonic_no_stitch_warning():
    m = st.identify(st.parse_example(HINTLESS_2BLOCK))
    al = st.align(m, st.extract_table_data(_table_reversed_order()))
    assert not any("not low-Q" in w for w in al.warnings)


# --- full pipeline --------------------------------------------------------

def test_fill_keeps_noninput_lines_byte_identical():
    res = st.fill_from_example(EXAMPLE, _table())
    assert res.ok, res.errors
    old = EXAMPLE.splitlines()
    new = res.new_source.splitlines()
    assert len(old) == len(new)
    changed = [i for i, (o, n) in enumerate(zip(old, new)) if o != n]
    # Every changed line must be an input-array assignment (starts with a known var).
    for i in changed:
        head = old[i].split("=")[0].strip()
        assert any(head.startswith(p) for p in
                   ("sample_names", "sample_thick", "samscatt", "samtrans",
                    "bkgscatt", "bkgtrans", "emptybeam")), old[i]


def test_fill_pulls_runs_from_table_and_parses():
    res = st.fill_from_example(EXAMPLE, _table())
    ast.parse(res.new_source)  # valid python
    ns: dict = {}
    # Exec only the top input block (up to the reduction code marker) to read arrays.
    header = res.new_source.split("# BELOW IS REDUCTION CODE")[0]
    # Drop the import lines that need drtsans; keep pure assignments.
    safe = "\n".join(l for l in header.splitlines()
                     if not l.startswith(("from ", "import ", "sys.path")))
    exec(safe, ns)
    assert ns["sample_names"] == [f"P{i+1}" for i in range(6)]
    assert ns["samscatt_0"] == [190000, 190001, 190002, 190003, 190004, 190005]
    assert ns["emptybeam_2"] == 190290           # scalar stays scalar
    assert ns["bkgscatt_1"] == [190180] * 6      # list stays list


def test_original_run_numbers_are_gone():
    res = st.fill_from_example(EXAMPLE, _table())
    # A run number unique to the example (186680) must not survive in the arrays.
    header = res.new_source.split("# BELOW IS REDUCTION CODE")[0]
    assert "186680" not in header and "186623" not in header


# --- validation catches problems -----------------------------------------

def test_empty_table_fails():
    res = st.fill_from_example(EXAMPLE, WorkingTable(name="default"))
    assert not res.ok and any("empty" in e for e in res.errors)


def test_non_eqvar_script_fails():
    res = st.fill_from_example("x = 1\ny = 2\n", _table())
    assert not res.ok and any("input arrays" in e for e in res.errors)


def test_nonrectangular_sample_set_warns():
    # config 3 (1.3m1a) is missing sample P6 → arrays would not line up.
    t = _table()
    for r in [row for row in t.rows if row.physical_configuration == "1.3m1a"
              and row.sample_name == "P6"]:
        t.rows.remove(r)
    res = st.fill_from_example(EXAMPLE, t)
    assert any("sample set differs" in w for w in res.warnings)


def test_fewer_configs_than_example_fails_closed():
    # Table has only 2 of the 4 configs the example expects — refuse rather than
    # emit a script that keeps the example's own runs in the unmatched blocks.
    res = st.fill_from_example(EXAMPLE, _table(configs=[(4, 10, 60), (2.5, 2.5, 60)]))
    assert not res.ok
    assert not res.new_source
    assert any("Configuration mismatch" in e for e in res.errors)
    assert any("no matching table config" in e for e in res.errors)


def test_extra_config_in_table_fails_closed():
    # Table has a config (8m10a) the example has no block for — its samples would
    # silently not be reduced. Refuse.
    res = st.fill_from_example(EXAMPLE, _table(configs=CONFIGS + [(8, 10, 60)]))
    assert not res.ok
    assert any("no block in the example" in e for e in res.errors)


def test_command_reports_mismatch(tmp_path):
    s = SessionState()
    s.ipts = 1
    s.output_directory = str(tmp_path)
    s.tables[s.active_table] = _table(configs=[(4, 10, 60), (2.5, 2.5, 60)])
    s.current_table.name = s.active_table
    res = _run(["--like", str(FIXTURE)], s)
    assert not res.success and "mismatch" in res.message.lower()
    assert not list(tmp_path.glob("*.py"))  # nothing written


# --- command wiring -------------------------------------------------------

def _run(args, st_):
    return asyncio.new_event_loop().run_until_complete(handle_export_script(args, st_))


def test_command_writes_file(tmp_path):
    s = SessionState()
    s.ipts = 38681
    s.output_directory = str(tmp_path)
    s.tables[s.active_table] = _table()
    s.current_table.name = s.active_table
    out = tmp_path / "filled.py"
    res = _run(["--like", str(FIXTURE), "-o", str(out)], s)
    assert res.success, res.message
    assert out.is_file()
    ast.parse(out.read_text())


def test_command_missing_example_errors(tmp_path):
    s = SessionState()
    s.tables[s.active_table] = _table()
    res = _run(["--like", str(tmp_path / "nope.py")], s)
    assert not res.success and "not found" in res.message


# --- LLM fallback for odd variable naming --------------------------------

# A script whose input arrays use names the heuristic does NOT recognise.
ODD_EXAMPLE = """\
ipts_number = 100
output_directory = "/x/"
snames = ['A', 'B']
sthick = [1, 1]
# 4m 10A
scatt_a = [10, 11]
trans_a = [12, 13]
bg_a = [14, 14]
bgt_a = [15, 15]
eb_a = 16
# BELOW IS REDUCTION CODE
for i in range(len(snames)):
    pass
"""


def _one_config_table():
    t = WorkingTable(name="default")
    for si, nm in enumerate(["A", "B"]):
        t.add_row(WorkingTableRow(
            index=0, scattering_run=str(500 + si), sample_name=nm,
            transmission_run=str(600 + si), background_scatt="700",
            background_trans="701", empty_beam="702",
            detector_distance=4.0, wavelength=10.0, frequency=60, thickness=1.0))
    return t


def test_heuristic_alone_cannot_identify_odd_names():
    res = st.fill_from_example(ODD_EXAMPLE, _one_config_table())
    assert not res.ok and any("input arrays" in e for e in res.errors)


def _stub_llm(model):
    return st.apply_llm_mapping(model, {
        "sample_names": "snames", "sample_thick": "sthick",
        "blocks": [{"index": 0, "config": "4m10a", "samscatt": "scatt_a",
                    "samtrans": "trans_a", "bkgscatt": "bg_a",
                    "bkgtrans": "bgt_a", "emptybeam": "eb_a"}],
    })


def test_llm_fallback_fills_odd_names():
    res = st.fill_from_example(ODD_EXAMPLE, _one_config_table(), llm_identify=_stub_llm)
    assert res.ok, res.errors
    ns: dict = {}
    header = res.new_source.split("# BELOW IS REDUCTION CODE")[0]
    exec(header, ns)
    assert ns["snames"] == ["A", "B"]
    assert ns["scatt_a"] == [500, 501]
    assert ns["eb_a"] == 702              # scalar preserved
    assert ns["bg_a"] == [700, 700]


def test_llm_fallback_only_runs_when_heuristic_empty():
    # On the normal example the heuristic already fills role_blocks, so the LLM
    # stub must NOT be consulted (it would raise if called).
    def _boom(model):
        raise AssertionError("LLM fallback should not run when heuristic succeeds")
    res = st.fill_from_example(EXAMPLE, _table(), llm_identify=_boom)
    assert res.ok


def test_apply_llm_mapping_ignores_unknown_names():
    model = st.identify(st.parse_example(ODD_EXAMPLE))
    ok = st.apply_llm_mapping(model, {
        "sample_names": "does_not_exist",
        "blocks": [{"index": 0, "samscatt": "also_missing"}],
    })
    assert not ok and model.sample_names is None


# --- --adapt: LLM structural revision for a config mismatch ----------------

def _table_2cfg():
    return _table(configs=[(4, 10, 60), (2.5, 2.5, 60)])


def _good_adapt_stub(prompt):
    """Stand in for a capable LLM: comment out blocks 0 & 3, rewire the stitch."""
    partial = prompt.split("SCRIPT:\n", 1)[1]
    out = partial.splitlines()

    def cmt(lo, hi):
        for i in range(lo, hi + 1):
            if out[i].strip() and not out[i].lstrip().startswith("#"):
                ind = out[i][:len(out[i]) - len(out[i].lstrip())]
                out[i] = ind + "# " + out[i].lstrip()

    def find(pred, s=0):
        for i in range(s, len(out)):
            if pred(out[i]):
                return i
        return -1

    for n, hdr in [(0, "#9m 15A"), (3, "#1.3m 1A")]:
        h = find(lambda l: l.strip() == hdr)
        e = find(lambda l: l.strip().startswith(f"emptybeam_{n}"), h)
        cmt(h, e)
        p = find(lambda l: f"config {n}'" in l)
        r = find(lambda l: l.strip() == "reduceNow(eq)", p)
        cmt(p, r)
        for i, l in enumerate(out):
            if re.match(rf"\s*iq{n}(_fn)?\s*=", l) and not l.lstrip().startswith("#"):
                ind = l[:len(l) - len(l.lstrip())]
                out[i] = ind + "# " + l.lstrip()
    for i, l in enumerate(out):
        if "stitch_profiles(" in l and "iq0" in l:
            out[i] = re.sub(r"stitch_profiles\(.*?\)",
                            "stitch_profiles([iq1, iq2], overlap[2:4], target_profile_index=0)",
                            l) + "  # attn. verify stitch overlaps/target"
    return "\n".join(out) + "\n"


def test_adapt_good_revision_passes_and_flags_stitch():
    res = st.adapt_from_example(EXAMPLE, _table_2cfg(), llm_call=_good_adapt_stub)
    assert res.ok, res.errors
    assert res.review_required
    ast.parse(res.new_source)
    assert any("stitch_profiles([iq1, iq2]" in a for a in res.attn)
    # removed configs' runs survive only as commented-out lines, never active.
    active = [l for l in res.new_source.splitlines()
              if l.strip() and not l.lstrip().startswith("#")]
    assert not any("186680" in l or "186644" in l for l in active)


def test_adapt_rejects_edit_outside_stitch():
    def bad(prompt):
        return _good_adapt_stub(prompt).replace("eq._numqbins = 300", "eq._numqbins = 999")
    res = st.adapt_from_example(EXAMPLE, _table_2cfg(), llm_call=bad)
    assert not res.ok
    assert any("outside the stitch call" in e for e in res.errors)


def test_adapt_rejects_stale_removed_runs():
    def bad(prompt):  # returns the partial unchanged — removed blocks still active
        return prompt.split("SCRIPT:\n", 1)[1]
    res = st.adapt_from_example(EXAMPLE, _table_2cfg(), llm_call=bad)
    assert not res.ok
    assert any("removed config still referenced" in e for e in res.errors)


def test_adapt_requires_llm():
    res = st.adapt_from_example(EXAMPLE, _table_2cfg(), llm_call=lambda p: None)
    assert not res.ok and any("configured LLM" in e for e in res.errors)


def test_adapt_is_noop_when_configs_match():
    # No mismatch → adapt should just defer to the deterministic fill (no LLM).
    def _boom(p):
        raise AssertionError("LLM must not be called when configs already match")
    res = st.adapt_from_example(EXAMPLE, _table(), llm_call=_boom)
    assert res.ok and not res.review_required


def test_command_adapt_without_llm_fails_gracefully(tmp_path):
    s = SessionState()
    s.ipts = 1
    s.output_directory = str(tmp_path)
    s.tables[s.active_table] = _table_2cfg()
    s.current_table.name = s.active_table
    # No LLM configured in the test env → --adapt should fail, write nothing.
    res = _run(["--like", str(FIXTURE), "--adapt"], s)
    assert not res.success
    assert not list(tmp_path.glob("*.py"))


def test_command_deterministic_header_present(tmp_path):
    s = SessionState()
    s.ipts = 38681
    s.output_directory = str(tmp_path)
    s.tables[s.active_table] = _table()
    s.current_table.name = s.active_table
    out = tmp_path / "filled.py"
    res = _run(["--like", str(FIXTURE), "-o", str(out)], s)
    assert res.success
    text = out.read_text()
    assert "CHANGED (refilled from the working table)" in text
    assert "KEPT VERBATIM" in text
    ast.parse(text)  # header is comments, still parses


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
