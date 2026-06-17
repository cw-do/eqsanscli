"""Run matching service — groups by configuration and matches trans/bkg/empty.

Configuration = (detector_distance, wavelength, chopper_frequency).
All scattering runs (including bkg/empty) appear in the working table.
Transmission is matched for ALL scattering runs by sample name.

Run classification is stored in the catalog's ``run_class`` column (added at
catalog-load time) so that users can override it with ``/reclass`` before
running ``/matchruns``.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import pandas as pd

from eqsanscli.models.working_table import WorkingTable, WorkingTableRow

logger = logging.getLogger(__name__)

BKG_KEYWORDS = ["bkg", "banjo", "background", "emptycell", "emptyticell", "empty ticell",
                "empty ti-cell", "ti-cell", "ticell"]
# Empty beam patterns: "empty", "emp", "emt" as standalone words, or followed by "beam"
# Must NOT match "emptycell", "emptyticell", etc. (those are background)
_EMPTY_BEAM_RE = re.compile(
    r"\b(?:empty\s+beam|emp\s+beam|emt\s+beam|empty|emp|emt)\b", re.IGNORECASE
)

# Valid run_class values (canonical names used internally)
VALID_RUN_CLASSES = {
    "scattering", "transmission",
    "bkg_scatt", "bkg_trans",
    "empty_trans", "empty_scatt",
    "ignore",
}

# User-friendly short names → canonical
RUN_CLASS_ALIASES: dict[str, str] = {
    "scatt": "scattering",
    "s": "scattering",
    "trans": "transmission",
    "t": "transmission",
    "bkg": "bkg_scatt",
    "bkgscatt": "bkg_scatt",
    "bkg_scatt": "bkg_scatt",
    "bkgtrans": "bkg_trans",
    "bkg_trans": "bkg_trans",
    "empty": "empty_trans",
    "emptytrans": "empty_trans",
    "empty_trans": "empty_trans",
    "emptyscatt": "empty_scatt",
    "empty_scatt": "empty_scatt",
    "scattering": "scattering",
    "transmission": "transmission",
    "i": "ignore",
    "n": "ignore",
    "ignore": "ignore",
    "ignored": "ignore",
    "notused": "ignore",
    "not_used": "ignore",
    "skip": "ignore",
    "exclude": "ignore",
}

# Short display labels for /show catalog
RUN_CLASS_SHORT: dict[str, str] = {
    "scattering": "S",
    "transmission": "T",
    "bkg_scatt": "BkgS",
    "bkg_trans": "BkgT",
    "empty_trans": "EmpT",
    "empty_scatt": "EmpS",
    "ignore": "N",
}

ConfigKey = tuple[float, float, int]


@dataclass
class ClassifiedRun:
    run_number: int
    title: str
    detector_distance: float
    wavelength: float
    frequency: int
    run_type: str
    sample_name: str
    config_key: ConfigKey
    is_background: bool = False
    is_empty: bool = False


def _round_config(distance: float, wavelength: float, frequency: int) -> ConfigKey:
    return (round(distance, 1), round(wavelength, 1), frequency)


def classify_title(title: str) -> str:
    """Classify a run based on its title string.

    Returns one of the canonical run_class values:
        scattering, transmission, bkg_scatt, bkg_trans, empty_trans, empty_scatt

    Classification priority:
        1. Background keywords checked FIRST (emptycell/emptyticell/ti-cell/banjo/bkg)
        2. Empty beam (standalone "empty"/"emp"/"emt" or "* beam")
        3. S-/T- prefix for scattering/transmission
        4. Default: scattering
    """
    title_lower = title.strip().lower()
    is_scattering = title_lower.startswith("s-") or title_lower.startswith("s ")
    is_transmission = title_lower.startswith("t-") or title_lower.startswith("t ")

    # Check background BEFORE empty beam — "emptyticell" must be bkg, not empty
    is_background = any(kw in title_lower for kw in BKG_KEYWORDS)

    # Empty beam: standalone "empty"/"emp"/"emt" or "* beam" (word boundary prevents
    # matching "emptycell", "emptyticell" etc.)
    is_empty = bool(_EMPTY_BEAM_RE.search(title_lower)) and not is_background

    if is_empty and is_transmission:
        return "empty_trans"
    if is_empty and is_scattering:
        return "empty_scatt"
    if is_empty:
        return "empty_trans"
    if is_background and is_scattering:
        return "bkg_scatt"
    if is_background and is_transmission:
        return "bkg_trans"
    if is_background:
        return "bkg_scatt"
    if is_scattering:
        return "scattering"
    if is_transmission:
        return "transmission"
    return "scattering"


def add_run_class_column(df: pd.DataFrame) -> pd.DataFrame:
    """Add a ``run_class`` column to a catalog DataFrame based on titles.

    If the column already exists (e.g. loaded from a saved session), existing
    values are preserved — only missing/empty entries are filled in.
    """
    if "run_class" not in df.columns:
        df["run_class"] = df["title"].apply(lambda t: classify_title(str(t)))
    else:
        mask = df["run_class"].isna() | (df["run_class"] == "")
        df.loc[mask, "run_class"] = df.loc[mask, "title"].apply(
            lambda t: classify_title(str(t))
        )
    return df


def resolve_run_class(name: str) -> str | None:
    """Resolve a user-provided class name to a canonical run_class value.

    Returns None if the name is not recognized.
    """
    return RUN_CLASS_ALIASES.get(name.lower().strip())


def _classify_run_from_row(row) -> ClassifiedRun:
    """Build a ClassifiedRun from a catalog row that already has run_class."""
    run_type = str(row.get("run_class", "scattering"))
    if run_type not in VALID_RUN_CLASSES:
        run_type = classify_title(str(row.get("title", "")))
    is_background = run_type in ("bkg_scatt", "bkg_trans")
    is_empty = run_type in ("empty_trans", "empty_scatt")
    distance = float(row.get("detector_distance") or 0)
    wavelength = float(row.get("wavelength") or 0)
    frequency = int(row.get("frequency") or 60)

    return ClassifiedRun(
        run_number=int(row["run_number"]),
        title=str(row.get("title", "")),
        detector_distance=distance,
        wavelength=wavelength,
        frequency=frequency,
        run_type=run_type,
        sample_name=_extract_sample_name(str(row.get("title", ""))),
        config_key=_round_config(distance, wavelength, frequency),
        is_background=is_background,
        is_empty=is_empty,
    )


def _extract_sample_name(title: str) -> str:
    """Extract a clean sample name from an ONCat run title.

    Handles variable ordering:
      "r0.1 8m 12A 90C"  → "r0.1_90C"
      "r1 110C 4m 10A"   → "r1_110C"
      "r1 temp=110c 4m 10A" → "r1_110C"
      "S-abc 4m 10A 1.5C" → "abc" (thickness stripped)
    """
    s = title.strip()
    s = re.sub(r"^[sStT][-\s]+", "", s)

    # Extract temperature before stripping config — preserve for sample name.
    # "110C", "90C" (≥10 whole number) or "temp=XXX", "temp XXX".
    temp = ""
    m = re.search(r"\btemp\s*[=:]?\s*(\d+)\s*[cC]?\b", s, re.IGNORECASE)
    if not m:
        m = re.search(r"\b(\d{2,3})\s*[cC]\b", s)
    if m:
        temp = m.group(1) + "C"
        s = s[:m.start()] + s[m.end():]

    # Strip detector/wavelength/frequency config: "4m 10A", "2.5m 2.5a", "4m 10a 60Hz", etc.
    # Handles various orderings and is non-greedy (stops at next token boundary).
    s = re.sub(r"\s*\d+\.?\d*\s*m\s+\d+\.?\d*\s*[aA]\s*(?:\d+Hz)?", " ", s)

    # Strip thickness: small decimals at end like "1.5C", "0.1C" (≤10.0, at least one digit after dot or 0.x).
    s = re.sub(r"\s+\d+\.\d+\s*[cC]\s*$", "", s)
    s = re.sub(r"\s+0\.\d+\s*[cC]\s*$", "", s)

    s = re.sub(r"\s+", " ", s).strip()
    parts = [p for p in s.split(" ") if p]
    if temp:
        parts.append(temp)
    result = "_".join(parts)
    result = re.sub(r"_+", "_", result).strip("_")
    return result or title.strip()


def _classify_catalog(catalog: pd.DataFrame) -> list[ClassifiedRun]:
    """Classify all runs in a catalog using the run_class column.

    If run_class is missing, falls back to title-based classification.
    """
    if "run_class" not in catalog.columns:
        catalog = add_run_class_column(catalog)

    classified: list[ClassifiedRun] = []
    for _, row in catalog.iterrows():
        if str(row.get("run_class", "")) == "ignore":
            continue
        cr = _classify_run_from_row(row)
        classified.append(cr)
    return classified


def match_runs(catalog: pd.DataFrame, ipts: int = 0) -> tuple[WorkingTable, list[str]]:
    """Auto-match runs from a catalog into a working table.

    Returns (table, warnings) where warnings is a list of human-readable
    warning strings (e.g. multiple empty beams per config).

    - ALL scattering runs in the table (including bkg/empty).
    - Transmission matched for EVERY scattering run by sample name.
    - Bkg/empty scattering runs get empty beam as their own background.
    - Config = (distance, wavelength, frequency).
    """
    if catalog.empty:
        return WorkingTable(name="default", ipts=ipts), []

    classified = _classify_catalog(catalog)

    config_groups: dict[ConfigKey, list[ClassifiedRun]] = {}
    for cr in classified:
        config_groups.setdefault(cr.config_key, []).append(cr)

    table = WorkingTable(name="default", ipts=ipts)
    warnings: list[str] = []

    for config_key, runs in sorted(config_groups.items()):
        from eqsanscli.models.config_id import make_config_id
        cfg_label = make_config_id(config_key[0], config_key[1], config_key[2])

        all_scattering = [
            r for r in runs if r.run_type in ("scattering", "bkg_scatt", "empty_scatt")
        ]
        empty_trans_runs = [r for r in runs if r.run_type == "empty_trans"]
        bkg_scatt_runs = [r for r in runs if r.run_type == "bkg_scatt"]
        bkg_trans_runs = [r for r in runs if r.run_type == "bkg_trans"]

        if not all_scattering:
            continue

        # Warn if multiple empty beams in this config
        if len(empty_trans_runs) > 1:
            run_list = ", ".join(f"{r.run_number} ({r.title[:25]})" for r in empty_trans_runs)
            warnings.append(
                f"[{cfg_label}] {len(empty_trans_runs)} empty beam runs found: {run_list}\n"
                f"  Using {empty_trans_runs[0].run_number} as default. "
                f"Use /set <row> emp <run> to override."
            )

        # Warn if multiple background scattering runs in this config
        if len(bkg_scatt_runs) > 1:
            run_list = ", ".join(f"{r.run_number} ({r.title[:25]})" for r in bkg_scatt_runs)
            warnings.append(
                f"[{cfg_label}] {len(bkg_scatt_runs)} background scatt runs found: {run_list}\n"
                f"  Using {bkg_scatt_runs[0].run_number} as default. "
                f"Use /assign bkg <sample> to override."
            )

        default_empty = str(empty_trans_runs[0].run_number) if empty_trans_runs else ""
        default_bkg_scatt = str(bkg_scatt_runs[0].run_number) if bkg_scatt_runs else ""
        default_bkg_trans = str(bkg_trans_runs[0].run_number) if bkg_trans_runs else ""

        # Transmission lookup: ALL transmission-type runs indexed by sample name.
        # This ensures bkg/empty scattering runs find their T-banjo/T-empty matches.
        trans_lookup: dict[str, str] = {}
        trans_lookup_base: dict[str, str] = {}  # fallback: strip temperature for matching
        for r in runs:
            if r.run_type in ("transmission", "bkg_trans", "empty_trans"):
                trans_lookup[r.sample_name.lower()] = str(r.run_number)
                base = re.sub(r"_?\d{2,3}C$", "", r.sample_name, flags=re.IGNORECASE).lower()
                trans_lookup_base[base] = str(r.run_number)

        for s in all_scattering:
            trans_run = trans_lookup.get(s.sample_name.lower(), "")
            if not trans_run:
                # Fallback: strip temperature, match on base name
                s_base = re.sub(r"_?\d{2,3}C$", "", s.sample_name, flags=re.IGNORECASE).lower()
                trans_run = trans_lookup_base.get(s_base, "")

            if s.is_background or s.is_empty:
                # Background-cell and empty-beam rows don't get an auto-assigned
                # background — empty-beam is a calibration measurement, not a
                # background reference. User can /set <row> bkg <run> manually
                # if subtraction is desired for a specific bkg cell.
                row_bkg_scatt = ""
                row_bkg_trans = ""
            else:
                row_bkg_scatt = default_bkg_scatt
                row_bkg_trans = default_bkg_trans

            row = WorkingTableRow(
                index=0,
                scattering_run=str(s.run_number),
                sample_name=s.sample_name,
                transmission_run=trans_run,
                background_scatt=row_bkg_scatt,
                background_trans=row_bkg_trans,
                empty_beam=default_empty,
                detector_distance=s.detector_distance,
                wavelength=s.wavelength,
                frequency=s.frequency,
            )
            table.add_row(row)

    return table, warnings


def merge_new_runs(
    existing_table: WorkingTable,
    fresh_catalog: pd.DataFrame,
    ipts: int = 0,
) -> tuple[WorkingTable, list[str], int, list[str]]:
    """Merge new catalog runs into an existing working table.

    Preserves all existing rows (with their status, assignments, output_file).
    Adds only new scattering runs from the fresh catalog. New runs in existing
    configs inherit bkg/empty/bkgtrans from the existing table for that config.

    Returns:
        (merged_table, warnings, n_new_runs, new_config_ids)
    """
    from eqsanscli.models.config_id import make_config_id

    # Existing scattering run numbers
    existing_runs = {r.scattering_run for r in existing_table.rows}

    # Build fresh table from refreshed catalog
    fresh_table, fresh_warnings = match_runs(fresh_catalog, ipts=ipts)

    # Collect bkg/empty/bkgtrans assignments from existing table per config.
    # For each field, take the FIRST NON-EMPTY value across all rows in the
    # config — bkg-sample rows (e.g. banjo) deliberately have blank
    # background_scatt/background_trans, so simply taking the first row's
    # values would propagate those blanks to all new runs.
    config_assignments: dict[str, dict[str, str]] = {}
    for row in existing_table.rows:
        cfg = row.configuration
        assignments = config_assignments.setdefault(cfg, {
            "background_scatt": "",
            "background_trans": "",
            "empty_beam": "",
        })
        for field in ("background_scatt", "background_trans", "empty_beam"):
            if not assignments[field]:
                val = getattr(row, field, "")
                if val:
                    assignments[field] = val

    # Lookup: run_number → run_class. Used to skip bkg-inheritance for new
    # rows that are themselves bkg/empty samples (those rows deliberately have
    # blank bkg fields and should NOT inherit their own run as a background).
    bkg_like_classes = {"bkg_scatt", "bkg_trans", "empty_trans", "empty_scatt"}
    bkg_like_runs: set[str] = set()
    if "run_class" in fresh_catalog.columns and "run_number" in fresh_catalog.columns:
        for _, r in fresh_catalog.iterrows():
            if str(r.get("run_class", "")) in bkg_like_classes:
                bkg_like_runs.add(str(r["run_number"]))

    # Find new rows
    new_rows: list[WorkingTableRow] = []
    new_config_ids: set[str] = set()
    for row in fresh_table.rows:
        if row.scattering_run not in existing_runs:
            cfg = row.configuration
            if cfg in config_assignments and row.scattering_run not in bkg_like_runs:
                # Inherit assignments from existing table for this config
                assignments = config_assignments[cfg]
                row.background_scatt = assignments["background_scatt"]
                row.background_trans = assignments["background_trans"]
                row.empty_beam = assignments["empty_beam"]
            elif cfg not in config_assignments:
                # New config not seen before
                new_config_ids.add(cfg)
            new_rows.append(row)

    # Append new rows to existing table
    warnings: list[str] = []
    for row in new_rows:
        existing_table.add_row(row)

    if new_config_ids:
        warnings.append(
            f"New configuration(s) found: {', '.join(sorted(new_config_ids))}. "
            f"Presets will be applied for these."
        )

    return existing_table, warnings, len(new_rows), sorted(new_config_ids)


def assign_background(
    table: WorkingTable, catalog: pd.DataFrame, bkg_sample_name: str,
) -> tuple[int, str]:
    """Reassign background for all non-bkg samples using a named sample."""
    bkg_name_lower = bkg_sample_name.strip().lower()
    classified = _classify_catalog(catalog)

    bkg_scatt_by_config: dict[ConfigKey, str] = {}
    bkg_trans_by_config: dict[ConfigKey, str] = {}
    for cr in classified:
        if cr.sample_name.lower() == bkg_name_lower:
            if cr.run_type in ("scattering", "bkg_scatt", "empty_scatt"):
                bkg_scatt_by_config[cr.config_key] = str(cr.run_number)
            elif cr.run_type in ("transmission", "bkg_trans", "empty_trans"):
                bkg_trans_by_config[cr.config_key] = str(cr.run_number)

    if not bkg_scatt_by_config:
        return 0, f"No scattering runs found for sample '{bkg_sample_name}'."

    count = 0
    for trow in table.rows:
        cfg = trow.config_key
        if trow.sample_name.lower() == bkg_name_lower:
            # The bkg sample itself gets NO background — empty-beam is a
            # calibration measurement, not a real background reference.
            trow.set_field("background_scatt", "")
            trow.set_field("background_trans", "")
            count += 1
        else:
            new_bkg_scatt = bkg_scatt_by_config.get(cfg, "")
            new_bkg_trans = bkg_trans_by_config.get(cfg, "")
            if new_bkg_scatt:
                trow.set_field("background_scatt", new_bkg_scatt)
                count += 1
            if new_bkg_trans:
                trow.set_field("background_trans", new_bkg_trans)

    from eqsanscli.models.config_id import make_config_id
    configs_found = sorted(make_config_id(k[0], k[1], k[2]) for k in bkg_scatt_by_config)
    return count, (
        f"Assigned '{bkg_sample_name}' as background for {count} rows.\n"
        f"  Configs: {', '.join(configs_found)}"
    )
