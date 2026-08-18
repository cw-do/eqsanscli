"""Locating a run's NeXus file from its number alone.

Mantid resolves a run number against the SNS archive without being told which
experiment took it. So does this, and without needing Mantid: the archive layout
is fixed, so one glob over ``/SNS/EQSANS/IPTS-*`` finds the run in about a second
across the ~1100 experiment folders on disk.

Kept apart from any one algorithm because locating a run is not specific to
masks — anything that needs to read a run by number belongs here.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

logger = logging.getLogger(__name__)

#: Where the archive keeps run files. Newer experiments use `nexus/*.nxs.h5`,
#: experiments before ~2013 use `data/*.nxs`. The filename is exact rather than
#: globbed, so the `_ORIG.nxs.h5` copies some folders carry are not picked up.
ARCHIVE_PATTERNS = (
    "/SNS/EQSANS/IPTS-*/nexus/EQSANS_{run}.nxs.h5",
    "/SNS/EQSANS/IPTS-*/data/EQSANS_{run}.nxs",
)
def ipts_from_path(path: str) -> str:
    """The IPTS number in an archive path, or ''."""
    found = re.search(r"/IPTS-(\d+)/", path)
    return found.group(1) if found else ""
def find_run_in_archive(run: str) -> list[str]:
    """Every archive path holding this run, searched across all experiments.

    Mantid finds a run from its number alone, and so can we: the SNS archive
    layout is fixed, so one glob over `/SNS/EQSANS/IPTS-*` locates it without
    knowing which experiment took it. About 0.25 s over the ~1100 experiment
    folders on disk.
    """
    import glob as globmodule

    for pattern in ARCHIVE_PATTERNS:
        hits = sorted(globmodule.glob(pattern.format(run=run)))
        if hits:
            return hits          # modern layout first; do not pay for the rest
    return []
def resolve_run_file(run: str, ipts: object = None) -> tuple[Optional[str], list[str]]:
    """Locate a run's NeXus file. Returns (path, searched).

    The run number is enough: if it is not where the session's IPTS or the
    current folder would put it, the archive is searched for it, so `/mask create
    <run>` works before (or without) `/load ipts`.
    """
    if os.path.isabs(run) and os.path.exists(run):
        return run, [run]
    searched: list[str] = []
    candidates: list[str] = []
    if ipts:
        candidates.append(f"/SNS/EQSANS/IPTS-{ipts}/nexus/EQSANS_{run}.nxs.h5")
    candidates.append(os.path.abspath(f"EQSANS_{run}.nxs.h5"))
    for path in candidates:
        searched.append(path)
        if os.path.exists(path):
            return path, searched

    hits = find_run_in_archive(run)
    searched.append("/SNS/EQSANS/IPTS-*/{nexus,data}/EQSANS_%s.nxs[.h5]" % run)
    if hits:
        return hits[0], searched
    return None, searched
