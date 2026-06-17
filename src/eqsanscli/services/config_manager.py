"""Configuration manager — manages reduction parameters per config ID.

Each configuration (e.g., "4.0m 2.5A 60Hz") has its own set of reduction
parameters. Defaults are loaded from eqsans_reduction.json (the actual
drtsans template), so ALL parameters are visible and configurable.

Two-layer model: drtsans-template defaults < per-config user overrides.

The "preset" layer is no longer a separate runtime tier — JSON preset files
in preset_configs/ are auto-applied at /matchruns time (see commands/matching.py)
and become part of state.configurations. list_config_params() distinguishes
preset-derived values from explicit user edits by re-reading the matching
JSON preset and comparing values.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Special key in state.configurations for params that apply to ALL configs
# (set via "/set config all <param> <val>"). matchruns propagates these to each
# config it creates; per-config explicit values override.
ALL_CONFIGS_KEY = "__all__"

# Path to the canonical eqsans_reduction.json template
_JSON_TEMPLATE_PATH = "/SNS/EQSANS/shared/script/eqsanstools/eqsans_reduction.json"

# Cache for loaded defaults
_DEFAULTS_CACHE: dict[str, object] | None = None


def _load_json_defaults() -> dict[str, object]:
    """Load and flatten the configuration section from eqsans_reduction.json.

    Nested structures are flattened with dot notation:
      elasticReference.runNumber
      elasticReference.thickness
      elasticReference.transmission.runNumber
      scaleComponents.detector1
    """
    global _DEFAULTS_CACHE
    if _DEFAULTS_CACHE is not None:
        return _DEFAULTS_CACHE

    defaults: dict[str, object] = {}

    try:
        with open(_JSON_TEMPLATE_PATH) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        logger.warning("Could not load %s: %s. Using built-in defaults.", _JSON_TEMPLATE_PATH, e)
        _DEFAULTS_CACHE = _builtin_defaults()
        return _DEFAULTS_CACHE

    # Flatten the "configuration" block
    config_section = data.get("configuration", {})
    _flatten(config_section, "", defaults)

    _DEFAULTS_CACHE = defaults
    return defaults


def _flatten(obj: dict, prefix: str, result: dict[str, object]) -> None:
    """Recursively flatten a dict, using dot notation for nested keys."""
    for key, value in obj.items():
        flat_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            _flatten(value, flat_key, result)
        else:
            # Normalize key to lowercase for consistent lookup
            result[flat_key.lower()] = value


def _builtin_defaults() -> dict[str, object]:
    """Hardcoded fallback if eqsans_reduction.json is unavailable."""
    return {
        "outputdir": "./output/",
        "usetimeslice": False,
        "timesliceinterval": 300,
        "timesliceoffset": 0.0,
        "timesliceperiod": None,
        "uselogslice": False,
        "logslicename": None,
        "logsliceinterval": 10,
        "cuttofmin": 500.0,
        "cuttofmax": 3000.0,
        "wavelengthstep": 0.1,
        "wavelengthsteptype": "constant Delta lambda",
        "sampleoffset": "314.5",
        "usedetectoroffset": True,
        "detectoroffset": "0",
        "sampleaperturesize": 10,
        "sourceaperturediameter": None,
        "usepixelcalibration": None,
        "maskfilename": None,
        "usedefaultmask": None,
        "defaultmask": None,
        "usemaskbacktubes": None,
        "darkfilename": None,
        "normalization": "Total charge",
        "blockedbeamrunnumber": None,
        "fluxmonitorratiofile": None,
        "beamfluxfilename": None,
        "sensitivityfilename": None,
        "usesolidanglecorrection": True,
        "usethetadeptranscorrection": True,
        "mmradiusfortransmission": 25,
        "absolutescalemethod": None,
        "standardabsolutescale": 1.0,
        "numqxqybins": 80,
        "1dqbintype": "scalar",
        "qbintype": "linear",
        "numqbins": 120,
        "logqbinsperdecade": None,
        "uselogqbinsdecadecenter": False,
        "uselogqbinsevendecade": False,
        "wedgeminangles": "-30, 60",
        "wedgemaxangles": "30, 120",
        "autowedgeqmin": None,
        "autowedgeqmax": None,
        "autowedgeqdelta": None,
        "autowedgeazimuthaldelta": None,
        "autowedgepeakwidth": None,
        "autowedgebackgroundwidth": None,
        "autowedgesignaltonoisemin": None,
        "annularanglebin": 5.0,
        "qmin": None,
        "qmax": None,
        "useerrorweighting": None,
        "smearingpixelsizex": None,
        "smearingpixelsizey": None,
        "usesubpixels": None,
        "subpixelsx": None,
        "subpixelsy": None,
        "usesliceidxassuffix": None,
        "fitinelasticincoh": False,
        "selectminincoh": True,
        "incohfit_qmin": None,
        "incohfit_qmax": None,
        "incohfit_factor": None,
        "outputwavelengthdependentprofile": False,
        "incohfit_intensityweighted": False,
        "elasticreference.runnumber": None,
        "elasticreference.thickness": "1.0",
        "elasticreference.transmission.runnumber": None,
        "elasticreference.transmission.value": "0.9",
        "elasticreferencebkgd.runnumber": None,
        "elasticreferencebkgd.transmission.runnumber": None,
        "elasticreferencebkgd.transmission.value": "0.9",
        "scalecomponents.detector1": [1.002, 1.0728155533894388, 1],
    }


def _load_matching_preset(config_id: str) -> dict[str, object]:
    """Load the JSON preset that matches this config_id, dropping None values.

    Used for source attribution in list_config_params — lets us tell whether
    a value in user_configs came from preset auto-apply or an explicit /set.
    Returns {} if no preset matches or none is available.
    """
    from eqsanscli.services.preset_service import (
        find_closest_preset, list_presets, load_preset,
    )
    presets = list_presets()
    if not presets:
        return {}
    best, _ = find_closest_preset(config_id, [p["name"] for p in presets])
    if not best:
        return {}
    loaded = load_preset(best)
    if not loaded:
        return {}
    # Drop None values — those don't represent a meaningful preset setting.
    return {k: v for k, v in loaded.items() if v is not None}


def get_config(config_id: str, user_configs: dict[str, dict]) -> dict[str, object]:
    """Get the full configuration for a config ID.

    Two layers: drtsans-template defaults, then per-config user overrides
    (which includes preset values auto-applied at /matchruns time).
    """
    from eqsanscli.models.config_id import normalize_config_id
    result = dict(_load_json_defaults())
    norm = normalize_config_id(config_id)
    for key, overrides in user_configs.items():
        if key == ALL_CONFIGS_KEY:
            continue
        if normalize_config_id(key) == norm:
            result.update(overrides)
            break
    return result


def set_config_param(
    config_id: str, param: str, value: str, user_configs: dict[str, dict]
) -> tuple[bool, str]:
    """Set a single configuration parameter.

    Returns (success, message).
    """
    param_lower = param.lower()

    # Validate param exists in defaults or presets
    full_config = get_config(config_id, user_configs)
    if param_lower not in full_config:
        valid = sorted(full_config.keys())
        return False, f"Unknown parameter: {param}. Valid: {', '.join(valid)}"

    # Parse value based on current type
    current = full_config[param_lower]
    # Parameters that are boolean (based on eqsans_reduction.json)
    bool_params = {
        k for k, v in _load_json_defaults().items()
        if isinstance(v, bool)
    }
    # Sentinel values that clear a param back to None (drtsans treats null as "not set")
    if value.strip().lower() in ("none", "null"):
        parsed: object = None
    else:
        try:
            if isinstance(current, bool) or param_lower in bool_params:
                parsed = value.lower() in ("true", "1", "yes")
            elif isinstance(current, int) and not isinstance(current, bool):
                parsed = int(value)
            elif isinstance(current, float):
                parsed = float(value)
            elif current is None:
                # Try float, then int, then string
                try:
                    parsed = float(value)
                except ValueError:
                    parsed = value
            else:
                parsed = value
        except (ValueError, TypeError):
            return False, f"Invalid value for {param}: {value}"

    # Store override
    if config_id not in user_configs:
        user_configs[config_id] = {}
    user_configs[config_id][param_lower] = parsed

    return True, f"Set {param}={parsed} for config {config_id}."


def list_config_params(config_id: str, user_configs: dict[str, dict]) -> list[tuple[str, str, str]]:
    """List all parameters for a config with source info.

    Returns list of (param_name, value, source) where source is
    "default", "preset", or "user".

    Source attribution: a value in user_configs that matches the matching
    JSON preset's value is labeled "preset" (came from auto-apply); a value
    that differs is labeled "user" (explicit override). Values not in
    user_configs at all show as "default" (from the drtsans template).
    """
    from eqsanscli.models.config_id import normalize_config_id

    norm = normalize_config_id(config_id)
    user: dict[str, object] = {}
    for key, overrides in user_configs.items():
        if key == ALL_CONFIGS_KEY:
            continue
        if normalize_config_id(key) == norm:
            user = overrides
            break

    preset_values = _load_matching_preset(config_id)
    full = get_config(config_id, user_configs)

    result = []
    for param in sorted(full.keys()):
        val = full[param]
        if param in user:
            if param in preset_values and preset_values[param] == user[param]:
                source = "preset"
            else:
                source = "user"
        else:
            source = "default"
        result.append((param, str(val) if val is not None else "—", source))
    return result
