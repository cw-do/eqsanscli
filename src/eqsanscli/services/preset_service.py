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


def load_preset_raw(name: str) -> dict | None:
    """Return the full parsed JSON of a preset_configs/ file (NOT flattened).

    Used to display non-config presets like stitch_overlaps.json, which carry an
    ``overlaps`` list rather than a ``configuration`` section.
    """
    preset_dir = _find_preset_dir()
    if preset_dir is None:
        return None
    for path in (preset_dir / f"{name}.json", preset_dir / f"conf_{name}.json"):
        if path.is_file():
            try:
                with open(path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return None
    return None


def preset_dir_path() -> str | None:
    """Filesystem path of the preset_configs/ directory, for user-facing hints."""
    d = _find_preset_dir()
    return str(d) if d else None


def load_preset_from_file(path: str) -> dict[str, object] | None:
    """Load and flatten the configuration section from a reduction JSON at `path`.

    Returns None if the file is missing or not valid JSON. Unlike load_preset()
    this takes an explicit filesystem path, not a preset_configs/ name.
    """
    p = Path(path).expanduser()
    if not p.is_file():
        return None
    try:
        with open(p) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error("Failed to load preset file %s: %s", p, e)
        return None
    return _flatten_config(data)


def resolve_preset_source(
    name_or_path: str, base_dirs: list[str] | None = None,
) -> tuple[dict[str, object] | None, str, bool]:
    """Resolve a preset argument that may be a name OR a filesystem path.

    An existing .json file (as given, or resolved against cwd / any base_dir)
    wins over a same-named preset in preset_configs/, so a user can point
    /apply preset at their own reduction JSON. Falls back to the preset_configs/
    name lookup otherwise.

    Returns (params, label, is_file):
        params  — flattened configuration dict, or None if nothing resolved
        label   — the path (is_file) or the resolved preset name, for messages
        is_file — True when it came from an explicit file
    """
    candidates: list[Path] = []
    raw = Path(name_or_path).expanduser()
    candidates.append(raw)
    if not raw.is_absolute():
        candidates.append(Path.cwd() / raw)
        for b in base_dirs or []:
            candidates.append(Path(b).expanduser() / raw)

    for c in candidates:
        # Only treat as a file when it actually exists and looks like JSON —
        # a bare preset name like "conf_4m_10a_60hz" must not be caught here.
        if c.is_file() and c.suffix.lower() == ".json":
            params = load_preset_from_file(str(c))
            if params is not None:
                return params, str(c), True

    # Fall back to the preset_configs/ name resolution.
    resolved = get_preset_name_from_path(name_or_path)
    if resolved is not None:
        return load_preset(resolved), resolved, False
    return None, "", False


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


def find_closest_preset(config_id: str, preset_names: list[str]) -> tuple[str | None, str]:
    """Find the best matching preset for a config ID.

    Returns (preset_name, match_type) where match_type is
    'exact', 'partial', 'distance', or '' (no match).

    Priority:
      1. Exact match after normalization (e.g., 4m10a == conf_4m_10a_60hz)
      2. Substring match (e.g., 4m10a in conf_4m_10a_60hz)
      3. Same distance match (e.g., 4m2.5a → use 4m10a preset because both 4m)
    """
    import re
    from eqsanscli.models.config_id import normalize_config_id

    norm = normalize_config_id(config_id)

    for name in preset_names:
        if normalize_config_id(name) == norm:
            return name, "exact"

    for name in preset_names:
        n = normalize_config_id(name)
        if norm in n or n in norm:
            return name, "partial"

    dist_match = re.search(r"(\d+\.?\d*m)", norm)
    if dist_match:
        config_dist = dist_match.group(1)
        for name in preset_names:
            n = normalize_config_id(name)
            if config_dist in n:
                return name, "distance"

    return None, ""


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
