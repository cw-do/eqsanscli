"""Preset service — manages preset configuration files from preset_configs/ folder.

Presets are full eqsans_reduction.json files placed in the preset_configs/
folder. They are loaded, flattened (configuration section only), and can be
applied to active configurations or compared side-by-side.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Search paths for preset_configs folder
_PRESET_DIRS = [
    Path(__file__).resolve().parent.parent.parent.parent / "preset_configs",  # project root
    Path.cwd() / "preset_configs",  # current working directory
]


def _find_preset_dir() -> Path | None:
    """Find the preset_configs directory."""
    for d in _PRESET_DIRS:
        if d.is_dir():
            return d
    return None


def _flatten_config(data: dict) -> dict[str, object]:
    """Extract and flatten the 'configuration' section from a reduction JSON."""
    config_section = data.get("configuration", {})
    result: dict[str, object] = {}
    _flatten(config_section, "", result)
    return result


def _flatten(obj: dict, prefix: str, result: dict[str, object]) -> None:
    """Recursively flatten a dict using dot notation for nested keys."""
    for key, value in obj.items():
        flat_key = f"{prefix}{key}" if not prefix else f"{prefix}.{key}"
        if isinstance(value, dict):
            _flatten(value, flat_key, result)
        else:
            result[flat_key.lower()] = value


def list_presets() -> list[dict[str, str]]:
    """List all available presets.

    Returns list of {name, filename, description} dicts.
    """
    preset_dir = _find_preset_dir()
    if preset_dir is None:
        return []

    presets = []
    for f in sorted(preset_dir.glob("*.json")):
        name = f.stem  # e.g., "conf_4m_10a_60hz"
        # Try to extract a description from the file
        try:
            with open(f) as fh:
                data = json.load(fh)
            config = data.get("configuration", {})
            # Build a short description from key params
            desc_parts = []
            qbin = config.get("QbinType", "")
            nq = config.get("numQBins", "")
            qmin = config.get("Qmin", "")
            qmax = config.get("Qmax", "")
            incoh = config.get("fitInelasticIncoh", False)
            scale = config.get("StandardAbsoluteScale", "")
            if qbin:
                desc_parts.append(f"Q:{qbin}")
            if nq:
                desc_parts.append(f"bins:{nq}")
            if qmin and qmax:
                desc_parts.append(f"[{qmin}-{qmax}]")
            if incoh:
                desc_parts.append("incoh:on")
            if scale and scale != 1.0:
                desc_parts.append(f"scale:{scale:.4f}" if isinstance(scale, float) else f"scale:{scale}")
            desc = " | ".join(desc_parts) if desc_parts else ""
        except Exception:
            desc = "(error reading)"

        presets.append({"name": name, "filename": f.name, "description": desc})

    return presets


def load_preset(name: str) -> dict[str, object] | None:
    """Load a preset by name. Returns flattened configuration params, or None."""
    preset_dir = _find_preset_dir()
    if preset_dir is None:
        return None

    # Try exact filename match first
    candidates = [
        preset_dir / f"{name}.json",
        preset_dir / f"conf_{name}.json",
        preset_dir / name,
    ]
    for path in candidates:
        if path.is_file():
            try:
                with open(path) as f:
                    data = json.load(f)
                return _flatten_config(data)
            except (json.JSONDecodeError, OSError) as e:
                logger.error("Failed to load preset %s: %s", path, e)
                return None

    # Try fuzzy match on stem
    for f in preset_dir.glob("*.json"):
        if name.lower().replace("-", "_") in f.stem.lower():
            try:
                with open(f) as fh:
                    data = json.load(fh)
                return _flatten_config(data)
            except Exception:
                return None

    return None


def get_preset_name_from_path(name: str) -> str | None:
    """Resolve a preset name to the actual filename stem."""
    preset_dir = _find_preset_dir()
    if preset_dir is None:
        return None
    for path in [preset_dir / f"{name}.json", preset_dir / f"conf_{name}.json"]:
        if path.is_file():
            return path.stem
    for f in preset_dir.glob("*.json"):
        if name.lower().replace("-", "_") in f.stem.lower():
            return f.stem
    return None


def compare_configs(
    params_a: dict[str, object],
    params_b: dict[str, object],
    name_a: str = "A",
    name_b: str = "B",
) -> list[dict[str, str]]:
    """Compare two configuration parameter sets.

    Returns list of {param, value_a, value_b, diff} where diff is:
    - "same" — identical values
    - "diff" — different values
    - "only_a" — only in A
    - "only_b" — only in B
    """
    all_keys = sorted(set(params_a.keys()) | set(params_b.keys()))
    rows = []
    for key in all_keys:
        in_a = key in params_a
        in_b = key in params_b
        val_a = params_a.get(key)
        val_b = params_b.get(key)
        str_a = str(val_a) if val_a is not None else "—"
        str_b = str(val_b) if val_b is not None else "—"

        if not in_a:
            diff = "only_b"
        elif not in_b:
            diff = "only_a"
        elif str_a == str_b:
            diff = "same"
        else:
            diff = "diff"

        rows.append({
            "param": key,
            "value_a": str_a,
            "value_b": str_b,
            "diff": diff,
        })

    return rows
