"""/apply preset accepts an arbitrary JSON file path, not only preset_configs/ names.

Requested: "use this.json as the configuration parameters for 2.5m2.5a" — copy all
params from the user's own reduction JSON into a config. Previously only names in
preset_configs/ resolved, so an external file failed with "Preset not found".

    python -m pytest -q tests/test_apply_preset_file.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.commands.preset import handle_apply_preset
from eqsanscli.models.session_state import SessionState
from eqsanscli.services.preset_service import (
    load_preset_from_file,
    resolve_preset_source,
)


def _write_json(path: Path, config: dict):
    path.write_text(json.dumps({"configuration": config}))


def _run(args, state):
    return asyncio.new_event_loop().run_until_complete(handle_apply_preset(args, state))


# --- service layer --------------------------------------------------------

def test_load_from_file_flattens_and_skips_nothing(tmp_path):
    p = tmp_path / "r.json"
    _write_json(p, {"Qmin": 0.01, "elasticReference": {"Transmission": {"value": 0.9}}})
    params = load_preset_from_file(str(p))
    assert params == {"qmin": 0.01, "elasticreference.transmission.value": 0.9}


def test_load_from_file_missing_returns_none(tmp_path):
    assert load_preset_from_file(str(tmp_path / "nope.json")) is None


def test_resolve_prefers_existing_file_over_name(tmp_path):
    p = tmp_path / "custom.json"
    _write_json(p, {"Qmin": 0.02})
    params, label, is_file = resolve_preset_source(str(p))
    assert is_file and params == {"qmin": 0.02} and label == str(p)


def test_resolve_falls_back_to_preset_name():
    params, label, is_file = resolve_preset_source("conf_4m_10a_60hz")
    assert not is_file and params and label == "conf_4m_10a_60hz"


def test_resolve_unknown_returns_none():
    params, label, is_file = resolve_preset_source("definitely_not_a_preset")
    assert params is None and not is_file


# --- command layer --------------------------------------------------------

def test_apply_file_copies_all_params(tmp_path):
    p = tmp_path / "this.json"
    _write_json(p, {"Qmin": 0.01, "Qmax": 0.5, "numQBins": 33, "maskFileName": None})
    st = SessionState()
    st.configurations["2.5m2.5a"] = {}
    res = _run([str(p), "2.5m2.5a"], st)
    assert res.success, res.message
    cfg = st.configurations["2.5m2.5a"]
    # All non-null params copied; JSON null skipped.
    assert cfg == {"qmin": 0.01, "qmax": 0.5, "numqbins": 33}
    assert "file" in res.message


def test_apply_file_preserves_user_values_without_force(tmp_path):
    p = tmp_path / "this.json"
    _write_json(p, {"Qmin": 0.01, "Qmax": 0.5})
    st = SessionState()
    st.configurations["2.5m2.5a"] = {"qmin": 0.999}  # user-set
    _run([str(p), "2.5m2.5a"], st)
    assert st.configurations["2.5m2.5a"]["qmin"] == 0.999  # kept
    assert st.configurations["2.5m2.5a"]["qmax"] == 0.5     # filled


def test_apply_file_force_overwrites(tmp_path):
    p = tmp_path / "this.json"
    _write_json(p, {"Qmin": 0.01})
    st = SessionState()
    st.configurations["2.5m2.5a"] = {"qmin": 0.999}
    _run([str(p), "2.5m2.5a", "--force"], st)
    assert st.configurations["2.5m2.5a"]["qmin"] == 0.01


def test_apply_missing_json_path_errors(tmp_path):
    st = SessionState()
    st.configurations["2.5m2.5a"] = {}
    res = _run([str(tmp_path / "gone.json"), "2.5m2.5a"], st)
    assert not res.success and "Could not read" in res.message


def test_preset_name_still_works():
    st = SessionState()
    st.configurations["4m10a"] = {}
    res = _run(["conf_4m_10a_60hz", "4m10a"], st)
    assert res.success and len(st.configurations["4m10a"]) > 10
    assert "preset" in res.message


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
