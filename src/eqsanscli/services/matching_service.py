"""Run matching service — groups by configuration and matches trans/bkg/empty.

Configuration = (detector_distance, wavelength, chopper_frequency).
All scattering runs (including bkg/empty) appear in the working table.
Transmission is matched for ALL scattering runs by sample name.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import pandas as pd

from eqsanscli.models.working_table import WorkingTable, WorkingTableRow

logger = logging.getLogger(__name__)

BKG_KEYWORDS = ["bkg", "banjo", "background"]
EMPTY_KEYWORDS = ["empty", "emptybeam", "empty beam"]

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


def _classify_run(
    run_number: int, title: str, distance: float, wavelength: float, frequency: int = 60,
) -> ClassifiedRun:
    title_lower = title.strip().lower()
    is_scattering = title_lower.startswith("s-") or title_lower.startswith("s ")
    is_transmission = title_lower.startswith("t-") or title_lower.startswith("t ")
    is_empty = any(kw in title_lower for kw in EMPTY_KEYWORDS)
    is_background = any(kw in title_lower for kw in BKG_KEYWORDS)

    if is_empty and is_transmission:
        run_type = "empty_trans"
    elif is_empty and is_scattering:
        run_type = "empty_scatt"
    elif is_empty:
        run_type = "empty_trans"
    elif is_background and is_scattering:
        run_type = "bkg_scatt"
    elif is_background and is_transmission:
        run_type = "bkg_trans"
    elif is_background:
        run_type = "bkg_scatt"
    elif is_scattering:
        run_type = "scattering"
    elif is_transmission:
        run_type = "transmission"
    else:
        run_type = "scattering"

    return ClassifiedRun(
        run_number=run_number,
        title=title,
        detector_distance=distance,
        wavelength=wavelength,
        frequency=frequency,
        run_type=run_type,
        sample_name=_extract_sample_name(title),
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
    """Classify all runs in a catalog."""
    classified: list[ClassifiedRun] = []
    for _, row in catalog.iterrows():
        cr = _classify_run(
            run_number=int(row["run_number"]),
            title=str(row.get("title", "")),
            distance=float(row.get("detector_distance") or 0),
            wavelength=float(row.get("wavelength") or 0),
            frequency=int(row.get("frequency") or 60),
        )
        classified.append(cr)
    return classified


def match_runs(catalog: pd.DataFrame, ipts: int = 0) -> WorkingTable:
    """Auto-match runs from a catalog into a working table.

    - ALL scattering runs in the table (including bkg/empty).
    - Transmission matched for EVERY scattering run by sample name.
    - Bkg/empty scattering runs get empty beam as their own background.
    - Config = (distance, wavelength, frequency).
    """
    if catalog.empty:
        return WorkingTable(name="default", ipts=ipts)

    classified = _classify_catalog(catalog)

    config_groups: dict[ConfigKey, list[ClassifiedRun]] = {}
    for cr in classified:
        config_groups.setdefault(cr.config_key, []).append(cr)

    table = WorkingTable(name="default", ipts=ipts)

    for config_key, runs in sorted(config_groups.items()):
        all_scattering = [
            r for r in runs if r.run_type in ("scattering", "bkg_scatt", "empty_scatt")
        ]
        empty_trans_runs = [r for r in runs if r.run_type == "empty_trans"]
        bkg_scatt_runs = [r for r in runs if r.run_type == "bkg_scatt"]
        bkg_trans_runs = [r for r in runs if r.run_type == "bkg_trans"]

        if not all_scattering:
            continue

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
                row_bkg_scatt = default_empty
                row_bkg_trans = default_empty
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

    return table


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

    empty_by_config: dict[ConfigKey, str] = {}
    for trow in table.rows:
        if trow.empty_beam:
            empty_by_config[trow.config_key] = trow.empty_beam

    count = 0
    for trow in table.rows:
        cfg = trow.config_key
        if trow.sample_name.lower() == bkg_name_lower:
            trow.background_scatt = empty_by_config.get(cfg, "")
            trow.background_trans = empty_by_config.get(cfg, "")
            count += 1
        else:
            new_bkg_scatt = bkg_scatt_by_config.get(cfg, "")
            new_bkg_trans = bkg_trans_by_config.get(cfg, "")
            if new_bkg_scatt:
                trow.background_scatt = new_bkg_scatt
                count += 1
            if new_bkg_trans:
                trow.background_trans = new_bkg_trans

    from eqsanscli.models.config_id import make_config_id
    configs_found = sorted(make_config_id(k[0], k[1], k[2]) for k in bkg_scatt_by_config)
    return count, (
        f"Assigned '{bkg_sample_name}' as background for {count} rows.\n"
        f"  Configs: {', '.join(configs_found)}"
    )
