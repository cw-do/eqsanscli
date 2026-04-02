"""ONCat API wrapper — fetches experiment catalog data via pyoncat."""

from __future__ import annotations

import logging
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

# Machine-to-machine credentials for ONCat
CLIENT_ID = "17ddcb3e-a727-41a2-aec5-43533988ab69"
CLIENT_SECRET = "3027a2b1-da09-4e13-bf97-f389ff1a747f"

# Fields to fetch from ONCat
PROJECTION = [
    "experiment",
    "location",
    "indexed.run_number",
    "metadata.entry.title",
    "metadata.entry.run_number",
    "metadata.entry.total_counts",
    "metadata.entry.duration",
    "metadata.entry.daslogs.detectorz.average_value",
    "metadata.entry.daslogs.wavelength.average_value",
    "metadata.entry.daslogs.speed1.average_value",
    "metadata.entry.proton_charge",
]


def _round_frequency(raw_freq: float) -> int:
    """Round chopper frequency to nearest standard value (30 or 60 Hz)."""
    if raw_freq <= 0:
        return 60  # default
    if raw_freq < 45:
        return 30
    return 60


def _extract_field(record: Any, dotted_path: str) -> Any:
    """Safely extract a nested field from an ONCat record using dotted path.

    ONCat returns ONCatObject instances which support __getitem__ (bracket access)
    but nested objects may also be ONCatObject, not plain dicts.
    """
    obj = record
    for key in dotted_path.split("."):
        if obj is None:
            return None
        try:
            obj = obj[key]
        except (KeyError, TypeError, IndexError):
            try:
                obj = getattr(obj, key, None)
            except Exception:
                return None
    return obj


def fetch_catalog(ipts: int) -> pd.DataFrame:
    """Fetch all runs for an IPTS number from ONCat.

    Returns a DataFrame with columns:
        run_number, title, detector_distance, wavelength,
        total_counts, duration, proton_charge, experiment, location
    """
    try:
        import pyoncat
    except ImportError:
        raise ImportError(
            "pyoncat is required for ONCat access. "
            "Install it with: pip install pyoncat"
        )

    logger.info("Connecting to ONCat for IPTS-%d...", ipts)
    oncat = pyoncat.ONCat(
        "https://oncat.ornl.gov",
        flow=pyoncat.CLIENT_CREDENTIALS_FLOW,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
    )
    oncat.login()

    logger.info("Fetching catalog for IPTS-%d...", ipts)
    datafiles = oncat.Datafile.list(
        facility="SNS",
        instrument="EQSANS",
        experiment=f"IPTS-{ipts}",
        projection=PROJECTION,
        exts=[".nxs.h5"],
    )

    if not datafiles:
        logger.warning("No datafiles found for IPTS-%d", ipts)
        return pd.DataFrame()

    rows = []
    for record in datafiles:
        run_number = (
            _extract_field(record, "metadata.entry.run_number")
            or _extract_field(record, "indexed.run_number")
        )
        if run_number is None:
            continue

        rows.append(
            {
                "run_number": int(run_number),
                "title": _extract_field(record, "metadata.entry.title") or "",
                "detector_distance": float(
                    _extract_field(record, "metadata.entry.daslogs.detectorz.average_value") or 0
                ) / 1000.0,  # ONCat returns mm, convert to meters
                "wavelength": float(
                    _extract_field(record, "metadata.entry.daslogs.wavelength.average_value") or 0
                ),
                "total_counts": int(
                    _extract_field(record, "metadata.entry.total_counts") or 0
                ),
                "duration": int(
                    _extract_field(record, "metadata.entry.duration") or 0
                ),
                "frequency": _round_frequency(
                    float(
                        _extract_field(record, "metadata.entry.daslogs.speed1.average_value") or 60
                    )
                ),
                "proton_charge": float(
                    _extract_field(record, "metadata.entry.proton_charge") or 0
                ),
                "experiment": _extract_field(record, "experiment") or f"IPTS-{ipts}",
                "location": _extract_field(record, "location") or "",
            }
        )

    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("run_number").reset_index(drop=True)
    logger.info("Fetched %d runs for IPTS-%d", len(df), ipts)
    return df


_EXPERIMENT_PROJECTION = ["id", "title", "members", "rank", "size", "activity"]

# Module-level cache: stores the full list of experiment dicts fetched from ONCat.
# Persists for the lifetime of the process. Use list_experiments(refresh=True) to bust it.
_experiment_cache: list[dict] | None = None


def _fetch_all_experiments() -> list[dict]:
    try:
        import pyoncat
    except ImportError:
        raise ImportError("pyoncat is required for ONCat access.")

    oncat = pyoncat.ONCat(
        "https://oncat.ornl.gov",
        flow=pyoncat.CLIENT_CREDENTIALS_FLOW,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
    )
    oncat.login()

    logger.info("Fetching EQSANS experiment list from ONCat...")
    experiments = oncat.Experiment.list(
        facility="SNS",
        instrument="EQSANS",
        projection=_EXPERIMENT_PROJECTION,
    )

    results = []
    for exp in experiments:
        d = exp.to_dict()
        ipts_num = d.get("rank", 0)
        title = d.get("title", "") or ""
        members_list = d.get("members") or []
        member_names = [m.get("name", "") for m in members_list if isinstance(m, dict)]
        runs = d.get("size", 0)
        activity = d.get("activity") or {}
        dates = activity.get("acquisition") or []
        date_range = f"{dates[0]} — {dates[-1]}" if dates else ""
        results.append({
            "ipts": ipts_num,
            "title": title,
            "members": member_names,
            "runs": runs,
            "dates": date_range,
        })

    results.sort(key=lambda r: r["ipts"])
    logger.info("Fetched %d total EQSANS experiments from ONCat", len(results))
    return results


def list_experiments(search: str = "", refresh: bool = False) -> tuple[list[dict], bool]:
    """List EQSANS experiments, optionally filtered by text.

    Results are cached in memory after the first fetch. Subsequent calls with
    a different search term filter the cache without hitting the network.

    Args:
        search: Filter string. Use "*" or "" for all. Supports multi-term via
                "and" or "+" (e.g. "changwoo and sds"). Case-insensitive.
        refresh: If True, discard cache and re-fetch from ONCat.

    Returns:
        (results, from_cache) — matched experiment dicts, and whether cache was used.
    """
    global _experiment_cache

    if refresh or _experiment_cache is None:
        _experiment_cache = _fetch_all_experiments()
        was_cached = False
    else:
        was_cached = True

    import re as _re
    raw = search.strip().lower()
    terms = [t.strip() for t in _re.split(r"\+|\band\b", raw) if t.strip()]

    if not terms or terms == ["*"]:
        results = list(_experiment_cache)
    else:
        results = []
        for exp in _experiment_cache:
            searchable = (exp["title"] + " " + " ".join(exp["members"])).lower()
            if all(t in searchable for t in terms):
                results.append(exp)

    logger.info("Found %d experiments (filter=%r, cached=%s)", len(results), search, was_cached)
    return results, was_cached
