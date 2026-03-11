"""Configuration manager — manages reduction parameters per config ID.

Each configuration (e.g., "4.0m 2.5A 60Hz") has its own set of reduction
parameters. Defaults are loaded from eqsans_reduction.json (the actual
drtsans template), so ALL parameters are visible and configurable.

Priority: user overrides > preset > json defaults.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from eqsanscli.config.presets import CONFIG_PRESETS

logger = logging.getLogger(__name__)

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


def _find_preset(config_id: str) -> dict[str, object]:
    from eqsanscli.models.config_id import normalize_config_id
    import re
    norm = normalize_config_id(config_id)

    for key, preset in CONFIG_PRESETS.items():
        if normalize_config_id(key) == norm:
            return dict(preset)

    # Fallback: strip trailing frequency (30hz/60hz) and retry
    norm_no_freq = re.sub(r"\d+hz$", "", norm)
    for key, preset in CONFIG_PRESETS.items():
        key_no_freq = re.sub(r"\d+hz$", "", normalize_config_id(key))
        if key_no_freq == norm_no_freq:
            return dict(preset)

    return {}


def get_config(config_id: str, user_configs: dict[str, dict]) -> dict[str, object]:
    """Get the full configuration for a config ID.

    Priority: user overrides > preset > json defaults.
    """
    from eqsanscli.models.config_id import normalize_config_id
    result = dict(_load_json_defaults())
    preset = _find_preset(config_id)
    result.update(preset)
    norm = normalize_config_id(config_id)
    for key, overrides in user_configs.items():
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
    try:
        if isinstance(current, bool) or param_lower in bool_params:
            parsed: object = value.lower() in ("true", "1", "yes")
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
    """
    preset = _find_preset(config_id)
    user = user_configs.get(config_id, {})
    full = get_config(config_id, user_configs)

    result = []
    for param in sorted(full.keys()):
        val = full[param]
        if param in user:
            source = "user"
        elif param in preset:
            source = "preset"
        else:
            source = "default"
        result.append((param, str(val) if val is not None else "—", source))
    return result
