"""Builds drtsans-compatible eqsans_reduction.json from WorkingTableRow + config params."""

from __future__ import annotations

import copy
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TEMPLATE_PATH = "/SNS/EQSANS/shared/script/eqsanstools/eqsans_reduction.json"
_TEMPLATE_CACHE: dict | None = None


def _load_template() -> dict:
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is not None:
        return _TEMPLATE_CACHE
    try:
        with open(_TEMPLATE_PATH) as f:
            _TEMPLATE_CACHE = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        _TEMPLATE_CACHE = _minimal_template()
    return _TEMPLATE_CACHE


def _minimal_template() -> dict:
    return {
        "schemaStamp": "",
        "instrumentName": "EQSANS",
        "iptsNumber": "",
        "sample": {"runNumber": "", "thickness": 1.0, "transmission": {"runNumber": "", "value": None}},
        "background": {"runNumber": "", "transmission": {"runNumber": "", "value": None}},
        "emptyTransmission": {"runNumber": "", "value": None},
        "beamCenter": {"runNumber": ""},
        "outputFileName": "",
        "configuration": {},
    }


# Mapping from our flattened lowercase keys back to the JSON's original camelCase keys.
# Only needed for keys where lowercase != original (most config keys have mixed case).
_KEY_RESTORE = {}


def _build_key_restore_map(template_config: dict, prefix: str = "") -> None:
    for key, value in template_config.items():
        flat = f"{prefix}{key}".lower() if not prefix else f"{prefix}.{key}".lower()
        _KEY_RESTORE[flat] = (prefix, key)
        if isinstance(value, dict):
            p = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
            _build_key_restore_map(value, p)


def build_reduction_json(
    ipts: int,
    scattering_run: str,
    sample_name: str,
    transmission_run: str,
    background_scatt: str,
    background_trans: str,
    empty_beam: str,
    thickness: float,
    config_params: dict[str, Any],
    output_dir: str = "./output/",
    output_filename: str = "",
) -> dict:
    """Build a complete drtsans reduction JSON.

    Populates the top-level run fields from the working table row,
    and the configuration section from the resolved config parameters.
    """
    template = _load_template()
    data = copy.deepcopy(template)

    data["schemaStamp"] = datetime.now().isoformat()
    data["instrumentName"] = "EQSANS"
    data["iptsNumber"] = str(ipts)

    data["sample"]["runNumber"] = scattering_run
    data["sample"]["thickness"] = thickness
    _set_transmission(data["sample"]["transmission"], transmission_run)

    data["background"]["runNumber"] = background_scatt
    _set_transmission(data["background"]["transmission"], background_trans)

    data["emptyTransmission"]["runNumber"] = empty_beam
    data["beamCenter"]["runNumber"] = empty_beam

    if output_filename:
        data["outputFileName"] = output_filename
    else:
        first_run = scattering_run.split(",")[0].strip()
        data["outputFileName"] = f"EQSANS_{first_run}"

    _apply_config_params(data, config_params, output_dir)

    return data


def _set_transmission(trans_block: dict, value: str) -> None:
    """Set transmission — either a run number or a float value."""
    if not value:
        trans_block["runNumber"] = ""
        trans_block["value"] = ""
        return

    try:
        fval = float(value)
        if fval <= 1.0:
            trans_block["runNumber"] = ""
            trans_block["value"] = str(fval)
            return
    except ValueError:
        pass

    trans_block["runNumber"] = value
    trans_block["value"] = ""


def _apply_config_params(data: dict, config_params: dict[str, Any], output_dir: str) -> None:
    """Apply flattened config params back into the nested JSON configuration block."""
    config = data.get("configuration", {})

    if not _KEY_RESTORE:
        _build_key_restore_map(config)

    for flat_key, value in config_params.items():
        if value is None:
            continue
        if flat_key == "outputdir":
            continue

        if flat_key in _KEY_RESTORE:
            prefix, orig_key = _KEY_RESTORE[flat_key]
            _set_nested(config, prefix, orig_key, value)
        else:
            _set_by_case_insensitive_scan(config, flat_key, value)

    final_dir = str(config_params.get("outputdir", output_dir))
    config["outputDir"] = final_dir
    data["configuration"] = config
    data["dataDirectories"] = final_dir


def _set_nested(config: dict, prefix: str, key: str, value: Any) -> None:
    """Set a value in a nested dict using the dot-separated prefix path."""
    target = config
    if prefix:
        for part in prefix.split("."):
            if part not in target:
                target[part] = {}
            target = target[part]
    target[key] = value


def _set_by_case_insensitive_scan(config: dict, flat_key: str, value: Any) -> None:
    """Fallback: scan the config dict case-insensitively for the key."""
    parts = flat_key.split(".")

    if len(parts) == 1:
        for existing_key in config:
            if existing_key.lower() == flat_key:
                config[existing_key] = value
                return
        config[flat_key] = value
    elif len(parts) == 2:
        for existing_key in config:
            if existing_key.lower() == parts[0] and isinstance(config[existing_key], dict):
                sub = config[existing_key]
                for sk in sub:
                    if sk.lower() == parts[1]:
                        sub[sk] = value
                        return
                sub[parts[1]] = value
                return
    elif len(parts) == 3:
        for k1 in config:
            if k1.lower() == parts[0] and isinstance(config[k1], dict):
                for k2 in config[k1]:
                    if k2.lower() == parts[1] and isinstance(config[k1][k2], dict):
                        for k3 in config[k1][k2]:
                            if k3.lower() == parts[2]:
                                config[k1][k2][k3] = value
                                return


def save_reduction_json(data: dict, path: str) -> str:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=4)
    return path
