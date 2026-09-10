"""Config-clone / per-row-override behaviour.

Runs under pytest when available, or standalone:

    python tests/test_config_clone.py

Standalone mode is the normal way to run this — the project has no formal test
runner installed in .venv (see CLAUDE.md > Testing).
"""

from __future__ import annotations

import asyncio
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.commands.config import handle_config
from eqsanscli.commands.matching import handle_set
from eqsanscli.models.config_id import base_config_id, is_derived_config_id, parse_config_id
from eqsanscli.models.session_state import SessionState
from eqsanscli.models.working_table import WorkingTableRow
from eqsanscli.services.config_manager import _load_matching_preset, get_config


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _state() -> SessionState:
    """Session with two 4m10a rows and one 8m10a row, presets applied."""
    st = SessionState()
    st.ipts = 12345
    table = st.current_table
    table.ipts = 12345
    for run_no, name, dist in (("101", "SampA", 4.0), ("102", "SampB", 4.0), ("103", "SampC", 8.0)):
        table.add_row(WorkingTableRow(
            index=0, scattering_run=run_no, sample_name=name,
            detector_distance=dist, wavelength=10.0, frequency=60,
        ))
    for cfg in table.configurations:
        st.configurations[cfg] = dict(_load_matching_preset(cfg))
    return st


# --- config_id helpers -----------------------------------------------------

def test_base_config_id_extracts_physics():
    assert base_config_id("4m10a") == "4m10a"
    assert base_config_id("4m10a_v2") == "4m10a"
    assert base_config_id("4m10a-mask2") == "4m10a"
    assert base_config_id("porsil_8m10a") == "8m10a"
    assert base_config_id("8m12a30hz_v2") == "8m12a30hz"
    assert base_config_id("lowq") == ""


def test_parse_config_id_falls_back_to_base():
    assert parse_config_id("4m10a_v2") == (4.0, 10.0, 60)
    assert parse_config_id("lowq") == (0.0, 0.0, 60)


def test_clone_vs_typo_classification():
    # Autopilot Step 4b keeps clones and drops typo'd plain config IDs.
    assert is_derived_config_id("4m10a_v2") is True
    assert is_derived_config_id("9m8a") is False


# --- /config clone ---------------------------------------------------------

def test_clone_name_must_carry_source_physics():
    st = _state()
    r = _run(handle_config(["clone", "4m10a", "mask2"], st))
    assert not r.success and "must contain the source's config ID" in r.message
    r = _run(handle_config(["clone", "4m10a", "8m10a_v2"], st))
    assert not r.success
    assert "4m10a_v2" not in st.configurations


def test_clone_from_unknown_config_is_rejected():
    st = _state()
    assert not _run(handle_config(["clone", "9m9a", "9m9a_v2"], st)).success


def test_clone_reproduces_effective_config():
    st = _state()
    assert _run(handle_config(["clone", "4m10a", "4m10a_v2"], st)).success
    assert get_config("4m10a_v2", st.configurations) == get_config("4m10a", st.configurations)


def test_clone_carries_user_set_values():
    st = _state()
    st.configurations["4m10a"]["maskfilename"] = "/tmp/custom_mask.nxs"
    st.configurations["4m10a"]["numqbins"] = 33
    _run(handle_config(["clone", "4m10a", "4m10a_c2"], st))
    clone = get_config("4m10a_c2", st.configurations)
    assert clone["maskfilename"] == "/tmp/custom_mask.nxs"
    assert clone["numqbins"] == 33


def test_clone_onto_existing_name_is_rejected():
    st = _state()
    _run(handle_config(["clone", "4m10a", "4m10a_v2"], st))
    assert not _run(handle_config(["clone", "4m10a", "4m10a_v2"], st)).success


def test_clone_is_independent_of_source():
    st = _state()
    _run(handle_config(["clone", "4m10a", "4m10a_v2"], st))
    st.configurations["4m10a_v2"]["maskfilename"] = "/tmp/v2.nxs"
    assert get_config("4m10a", st.configurations).get("maskfilename") != "/tmp/v2.nxs"


# --- /set <row> cfg --------------------------------------------------------

def test_assign_and_clear_override():
    st = _state()
    _run(handle_config(["clone", "4m10a", "4m10a_v2"], st))
    assert _run(handle_set(["1", "cfg", "4m10a_v2"], st)).success

    row = st.current_table.get_row(1)
    assert row.configuration == "4m10a_v2"
    assert row.physical_configuration == "4m10a"

    assert _run(handle_set(["1", "cfg", "none"], st)).success
    assert st.current_table.get_row(1).configuration == "4m10a"


def test_override_must_match_row_physics():
    st = _state()
    _run(handle_config(["clone", "4m10a", "4m10a_v2"], st))
    r = _run(handle_set(["3", "cfg", "4m10a_v2"], st))  # row 3 is 8m10a
    assert not r.success and "SampC" in r.message
    assert st.current_table.get_row(3).configuration_override == ""


def test_override_marks_done_row_modified():
    st = _state()
    _run(handle_config(["clone", "4m10a", "4m10a_v2"], st))
    st.current_table.get_row(1).status = "done"
    _run(handle_set(["1", "cfg", "4m10a_v2"], st))
    assert st.current_table.get_row(1).status == "modified"


# --- naming stays physics-based -------------------------------------------

def test_output_stem_ignores_override():
    st = _state()
    _run(handle_config(["clone", "4m10a", "4m10a_v2"], st))
    _run(handle_set(["1", "cfg", "4m10a_v2"], st))
    assert st.current_table.get_row(1).output_stem == "SampA_4m10a"


def test_scan_output_dir_recovers_sample_and_config():
    from eqsanscli.services.merge_service import _scan_output_dir

    with tempfile.TemporaryDirectory() as d:
        for cfg in ("4m10a", "8m10a"):
            with open(os.path.join(d, f"SampA_{cfg}_Iq.dat"), "w") as f:
                f.write("# q i di\n0.01 1 0.1\n")
        scanned = _scan_output_dir(d)
        assert list(scanned) == ["SampA"]
        assert sorted(c for _, c, _, _ in scanned["SampA"]) == ["4m10a", "8m10a"]


def test_exported_script_names_files_by_physics():
    from eqsanscli.services.script_exporter import export_reduction_script

    st = _state()
    _run(handle_config(["clone", "4m10a", "4m10a_v2"], st))
    _run(handle_set(["--sample", "SampA", "cfg", "4m10a_v2"], st))
    with tempfile.TemporaryDirectory() as d:
        path = export_reduction_script(
            st.current_table, st.configurations, d, os.path.join(d, "reduce.py"), ipts=12345,
        )
        text = Path(path).read_text()
    assert "_filename = str(sample_names[i]) + '_4m10a'" in text
    assert "_4m10a_v2'" not in text          # clone label never reaches a filename
    assert "Configuration: 4m10a_v2" in text  # but its params still get a block


# --- physics heuristics resolve clones ------------------------------------

def test_preset_lookup_matches_base_config():
    assert _load_matching_preset("4m10a_v2") == _load_matching_preset("4m10a")


def test_autopilot_preset_match_identical_for_clone():
    from eqsanscli.services.autopilot import _find_closest_preset
    from eqsanscli.services.preset_service import list_presets

    names = [p["name"] for p in list_presets()]
    assert _find_closest_preset("4m10a_v2", names) == _find_closest_preset("4m10a", names)


def test_stitch_target_survives_clone_label():
    from eqsanscli.services.merge_service import _default_target_index

    assert _default_target_index(["2.5m2.5a", "4m10a_v2"]) == 1


# --- session round-trip ---------------------------------------------------

def test_override_survives_save_load_and_old_files_load():
    st = _state()
    _run(handle_config(["clone", "4m10a", "4m10a_v2"], st))
    _run(handle_set(["1", "cfg", "4m10a_v2"], st))
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "session.json")
        st.save(path)
        reloaded = SessionState.load(path)
    assert reloaded.current_table.get_row(1).configuration == "4m10a_v2"
    assert "4m10a_v2" in reloaded.configurations

    # A pre-override session file (no configuration_override key, plus a stale
    # unknown field) must still deserialize.
    row = WorkingTableRow.from_dict({
        "index": 1, "scattering_run": "101", "sample_name": "X", "legacy_field": 1,
    })
    assert row.configuration_override == ""


# --- command registration parity -----------------------------------------

def test_both_entry_points_register_the_same_commands():
    from eqsanscli.commands.registry import register_all
    from eqsanscli.commands.router import CommandRouter
    from eqsanscli.headless import _register_commands

    shared = CommandRouter()
    register_all(shared)
    assert "config" in shared.commands and "matchruns" in shared.commands

    headless = CommandRouter()
    _register_commands(headless, SessionState())
    assert set(shared.commands) - set(headless.commands) == set()


def _clone_state():
    from eqsanscli.commands.config import handle_set_config  # noqa: F401
    st = SessionState()
    # a clone stored under its raw name (underscore + uppercase), as /config clone keeps it
    st.configurations["4m2.5a30hz_TR"] = {"usetimeslice": False, "qbintype": "log"}
    st.current_table.add_row(WorkingTableRow(
        index=0, scattering_run="188043", sample_name="ab0-1_fs",
        detector_distance=4.0, wavelength=2.5, frequency=30,
        configuration_override="4m2.5a30hz_TR"))
    return st


def test_set_config_on_clone_name_lands_on_the_clone():
    from eqsanscli.commands.config import handle_set_config
    st = _clone_state()
    res = _run(handle_set_config(["4m2.5a30hz_TR", "usetimeslice", "True"], st))
    assert res.success
    # no phantom normalized key; the clone itself is updated
    assert "4m2.5a30hztr" not in st.configurations
    assert st.configurations["4m2.5a30hz_TR"]["usetimeslice"] is True
    # the row (and thus the reduction) sees it
    row = st.current_table.rows[0]
    assert get_config(row.configuration, st.configurations)["usetimeslice"] is True
    assert "4m2.5a30hz_TR" in res.message   # echoes the name the user typed


def test_set_config_normalized_form_also_resolves_to_clone():
    from eqsanscli.commands.config import handle_set_config
    st = _clone_state()
    # the normalized spelling the tool used to echo must map back to the clone
    _run(handle_set_config(["4m2.5a30hztr", "usetimeslice", "True"], st))
    assert "4m2.5a30hztr" not in st.configurations
    assert st.configurations["4m2.5a30hz_TR"]["usetimeslice"] is True


def test_show_config_reads_the_clone_value():
    from eqsanscli.commands.config import handle_set_config, handle_show_config
    st = _clone_state()
    _run(handle_set_config(["4m2.5a30hz_TR", "usetimeslice", "True"], st))
    res = _run(handle_show_config(["4m2.5a30hz_TR"], st))
    row = next(r for r in res.data["rows"] if r["Parameter"] == "usetimeslice")
    assert row["Value"] == "True"


# --- config list annotation + /config delete -------------------------------

def _phantom_state():
    st = _clone_state()  # has clone 4m2.5a30hz_TR + a row using it
    st.configurations["4m2.5a30hztr"] = {"usetimeslice": True}  # phantom leftover
    return st


def test_config_list_annotates_clone_and_flags_leftover():
    from eqsanscli.commands.config import handle_config
    res = _run(handle_config(["list"], _phantom_state()))
    msg = res.message
    assert "4m2.5a30hz_TR (4m2.5a30hztr)" in msg          # normalized id shown
    assert "Leftover configs" in msg                       # phantom surfaced
    assert "duplicate of 4m2.5a30hz_TR" in msg


def test_config_delete_phantom_leaves_clone_and_row():
    from eqsanscli.commands.config import handle_config
    st = _phantom_state()
    res = _run(handle_config(["delete", "4m2.5a30hztr"], st))
    assert res.success and "Deleted" in res.message
    assert "4m2.5a30hztr" not in st.configurations
    assert "4m2.5a30hz_TR" in st.configurations
    assert st.current_table.rows[0].configuration_override == "4m2.5a30hz_TR"


def test_config_delete_in_use_refuses_without_force():
    from eqsanscli.commands.config import handle_config
    st = _clone_state()
    res = _run(handle_config(["delete", "4m2.5a30hz_TR"], st))
    assert not res.success and "assigned to" in res.message
    assert "4m2.5a30hz_TR" in st.configurations


def test_config_delete_force_reverts_rows():
    from eqsanscli.commands.config import handle_config
    st = _clone_state()
    st.current_table.rows[0].status = "done"
    res = _run(handle_config(["delete", "4m2.5a30hz_TR", "--force"], st))
    assert res.success
    assert "4m2.5a30hz_TR" not in st.configurations
    row = st.current_table.rows[0]
    assert row.configuration_override == ""       # reverted to physics config
    assert row.status == "modified"               # stale → re-reduce


def test_config_delete_physical_config_refused():
    from eqsanscli.commands.config import handle_config
    st = SessionState()
    st.current_table.add_row(WorkingTableRow(
        index=0, scattering_run="1", sample_name="x",
        detector_distance=4.0, wavelength=10.0, frequency=60))
    res = _run(handle_config(["delete", "4m10a"], st))
    assert not res.success and "physical configuration" in res.message


def test_config_delete_rejects_all_key():
    from eqsanscli.commands.config import handle_config
    from eqsanscli.services.config_manager import ALL_CONFIGS_KEY
    st = SessionState()
    st.configurations[ALL_CONFIGS_KEY] = {"numqbins": 33}
    res = _run(handle_config(["delete", ALL_CONFIGS_KEY], st))
    assert not res.success


if __name__ == "__main__":
    tests = [(n, o) for n, o in sorted(globals().items())
             if n.startswith("test_") and callable(o)]
    failures = []
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as exc:  # noqa: BLE001 - standalone runner
            print(f"  FAIL  {name}: {exc}")
            failures.append(name)
    print(f"\n{len(tests) - len(failures)}/{len(tests)} passed"
          + (f" — FAILED: {', '.join(failures)}" if failures else ""))
    sys.exit(1 if failures else 0)
