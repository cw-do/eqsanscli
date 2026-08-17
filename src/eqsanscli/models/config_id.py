"""Configuration ID utilities — compact format and flexible matching.

Config IDs are compact lowercase strings:
  4m10a       (4.0m distance, 10.0A wavelength, 60Hz default)
  4m2.5a      (4.0m, 2.5A, 60Hz)
  2.5m2.5a    (2.5m, 2.5A, 60Hz)
  8m12a30hz   (8.0m, 12.0A, 30Hz — non-default freq shown)

Used consistently in table display, filenames, and commands.
"""

from __future__ import annotations


def _fmt_num(val: float) -> str:
    """Format a number: drop .0 when integer, keep decimal otherwise."""
    if val == int(val):
        return str(int(val))
    return f"{val:g}"


def make_config_id(distance: float, wavelength: float, frequency: int) -> str:
    """Create a compact config ID from numeric values.

    Examples:
        make_config_id(4.0, 10.0, 60) → "4m10a"
        make_config_id(4.0, 2.5, 60)  → "4m2.5a"
        make_config_id(2.5, 2.5, 60)  → "2.5m2.5a"
        make_config_id(1.3, 4.0, 60)  → "1.3m4a"
        make_config_id(8.0, 12.0, 30) → "8m12a30hz"
    """
    d = round(distance, 1)
    w = round(wavelength, 1)
    base = f"{_fmt_num(d)}m{_fmt_num(w)}a"
    if frequency != 60:
        base += f"{frequency}hz"
    return base


def normalize_config_id(raw: str) -> str:
    """Normalize user input for matching: lowercase, strip spaces/underscores."""
    return raw.strip().lower().replace(" ", "").replace("_", "")


def config_ids_match(a: str, b: str) -> bool:
    return normalize_config_id(a) == normalize_config_id(b)


def base_config_id(name: str) -> str:
    """Extract the physics config ID embedded in an arbitrary config name.

    A row can point at a *cloned* config via `configuration_override` (see
    `/config clone`), and clone names carry a suffix: "4m10a_v2",
    "4m10a-mask2", "porsil_8m10a". Physics-driven heuristics — preset
    matching, cycle-file discovery, low-Q-first stitch ordering — need the
    underlying "4m10a" / "8m10a", not the clone label.

    Returns the canonical ID (via `make_config_id`, so "4.0m10.0a" → "4m10a"),
    or "" when the name contains no config ID at all.

    Examples:
        base_config_id("4m10a")          → "4m10a"
        base_config_id("4m10a_v2")       → "4m10a"
        base_config_id("porsil_8m10a")   → "8m10a"
        base_config_id("8m12a30hz_v2")   → "8m12a30hz"
        base_config_id("lowq")           → ""
    """
    import re

    m = re.search(r"(\d+\.?\d*)m(\d+\.?\d*)a(?:(\d+)hz)?", normalize_config_id(name))
    if not m:
        return ""
    return make_config_id(
        float(m.group(1)), float(m.group(2)), int(m.group(3)) if m.group(3) else 60
    )


def is_derived_config_id(name: str) -> bool:
    """True when `name` is a clone/variant label rather than a bare config ID.

    "4m10a" → False (it *is* the physics ID); "4m10a_v2" → True; "lowq" → True.
    Used to tell user-created clones apart from typo'd config IDs.
    """
    base = base_config_id(name)
    return not base or normalize_config_id(base) != normalize_config_id(name)


def parse_config_id(config_id: str) -> tuple[float, float, int]:
    """Parse a config ID string back into (distance, wavelength, frequency).

    Falls back to the embedded base ID (see `base_config_id`) so clone names
    still resolve to real physics instead of (0.0, 0.0, 60).

    Examples:
        parse_config_id("4m10a")        → (4.0, 10.0, 60)
        parse_config_id("2.5m2.5a")     → (2.5, 2.5, 60)
        parse_config_id("8m12a30hz")    → (8.0, 12.0, 30)
        parse_config_id("4m10a_v2")     → (4.0, 10.0, 60)
    """
    import re

    s = config_id.strip().lower()
    m = re.match(r"^(\d+\.?\d*)m(\d+\.?\d*)a(?:(\d+)hz)?$", s)
    if not m:
        base = base_config_id(config_id)
        if not base or normalize_config_id(base) == normalize_config_id(config_id):
            return (0.0, 0.0, 60)
        return parse_config_id(base)
    distance = float(m.group(1))
    wavelength = float(m.group(2))
    frequency = int(m.group(3)) if m.group(3) else 60
    return (distance, wavelength, frequency)


def find_matching_config(query: str, available: list[str]) -> str | None:
    norm_query = normalize_config_id(query)
    for config_id in available:
        if normalize_config_id(config_id) == norm_query:
            return config_id
    return None
