"""Per-frame incoherent-fit parameters in frame-skipping mode (v0.53.1).

drtsans reads fitInelasticIncoh / incohfit_qmin / incohfit_qmax / incohfit_factor /
incohfit_intensityweighted as one value for both frames or a list
[frame 0 (skip, long λ, low Q), frame 1 (lead, short λ, high Q)]
(tof/eqsans/correction_api.listify_incohfit_parameter). `/set config` stored
"0.02,0.10" as a string drtsans cannot use, and "true,false" as False.

    python -m pytest -q tests/test_per_frame_params.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from eqsanscli.integrations.json_builder import build_reduction_json
from eqsanscli.services.config_manager import get_config, set_config_param

CFG = "4m2.5a30hz"


def _set(param, value):
    uc: dict = {}
    ok, msg = set_config_param(CFG, param, value, uc)
    return ok, uc.get(CFG, {}).get(param), msg


def _json(param, value):
    uc: dict = {}
    assert set_config_param(CFG, param, value, uc)[0]
    d = build_reduction_json(ipts=1, scattering_run="1", sample_name="s", transmission_run="",
                             background_scatt="", background_trans="", empty_beam="2",
                             thickness=0.1, config_params=get_config(CFG, uc),
                             output_dir="/tmp", output_filename="s")
    c = d["configuration"]
    return next(v for k, v in c.items() if k.lower() == param)


def test_one_value_is_both_frames():
    assert _set("incohfit_qmin", "0.08")[1] == 0.08
    assert _set("fitinelasticincoh", "true")[1] is True


def test_two_values_become_a_real_list_in_every_spelling():
    for v in ("0.02,0.10", "[0.02, 0.10]", "0.02 0.10", "(0.02,0.1)"):
        assert _set("incohfit_qmin", v)[1] == [0.02, 0.1], v
    assert _json("incohfit_qmax", "0.04,0.25") == [0.04, 0.25]


def test_flag_pair_no_longer_collapses_to_false():
    assert _set("fitinelasticincoh", "true,false")[1] == [True, False]
    assert _json("fitinelasticincoh", "false,true") == [False, True]


def test_none_clears_one_frame():
    assert _set("incohfit_qmin", "0.02,none")[1] == [0.02, None]


def test_bad_input_is_refused_not_stored():
    for v in ("0.1,0.2,0.3", "abc", "0", "-0.1,0.2"):
        ok, stored, msg = _set("incohfit_qmin", v)
        assert not ok and stored is None, v
    assert not _set("fitinelasticincoh", "maybe")[0]


def test_message_names_the_frames():
    msg = _set("incohfit_qmin", "0.02,0.1")[2]
    assert "frame 0" in msg and "low-Q" in msg and "frame 1" in msg
