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
                "empty ti-cell", "ti-cell", "ticell",
                # rheo-SANS: the empty Couette cup (IPTS-37681 "EmptyCupBob")
                "emptycup", "empty cup", "empty_cup"]
# Empty beam patterns: "empty"/"emp"/"emt" joined to "beam" by any separator or
# none ("empty beam", "emptybeam", "empty_beam", "emptyBeam"), OR standalone
# "empty"/"emp"/"emt" as a whole word. Must NOT match "emptycell"/"emptyticell"
# etc. — those have no word boundary after "empty" and are caught as background first.
_EMPTY_BEAM_RE = re.compile(
    # empty beam / emptybeam / empty_beam / emptyBeam — letter-boundaries, not \b,
    # because an underscore is a \w char so "beam\b" would fail before "_4m".
    r"(?<![a-z])(?:empty|emp|emt)[\s_-]*beam(?![a-z])"
    r"|\b(?:empty|emp|emt)\b",            # standalone empty / emp / emt
    re.IGNORECASE,
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

# Title tokens written by a proposal-driven script generator (protocol BKG-04,
# TBL-08). A background titled `bkg<N>…` is background number N; a sample that
# carries `bg<N>` wants that background. The sample-side pointer is `bg`, not
# `bkg`, because any title containing "bkg" is classified as a background.
# `th<X>mm` is the cell path length ('p' for a decimal point: th0p5mm).
# Tokens are underscore/space-delimited words inside the extracted sample name,
# so a title without them is matched exactly as before.
_BKG_ID_RE = re.compile(r"(?:^|_)bkg(\d+)(?=_|$)", re.IGNORECASE)
_BG_PTR_RE = re.compile(r"(?:^|_)bg(\d+)(?=_|$)", re.IGNORECASE)
_THICK_RE = re.compile(r"(?:^|_)th(\d+(?:p\d+)?)mm(?=_|$)", re.IGNORECASE)
_TEMP_SUFFIX_RE = re.compile(r"_(\d{2,3}C)$", re.IGNORECASE)

# A configuration written as one word: distance m wavelength a, '.' or 'p' as
# the decimal point, optional frame-skipping / frequency suffix.
_CFG_BODY = r"^\d+(?:[.p]\d+)?m\d+(?:[.p]\d+)?a(?:fs)?(?:\d+hz)?(?:fs)?"
# ...as a whole word in a title (delimited by whitespace, '_' or the ends).
_CFG_WORD_RE = re.compile(r"(?<![^\s_])" + _CFG_BODY[1:] + r"(?![^\s_])", re.IGNORECASE)


def title_thickness_cm(sample_name: str) -> float | None:
    """Cell thickness in cm from a `th<X>mm` token, or None when absent."""
    m = _THICK_RE.search(sample_name)
    if not m:
        return None
    return float(m.group(1).replace("p", ".")) / 10.0


def background_pointer(sample_name: str) -> int | None:
    """N from a sample's `bg<N>` token, or None."""
    m = _BG_PTR_RE.search(sample_name)
    return int(m.group(1)) if m else None


def _pick_numbered_background(n: int, sample_name: str,
                              bkg_scatt: list["ClassifiedRun"],
                              bkg_trans: list["ClassifiedRun"]) -> tuple[str, str, str]:
    """(bkg_scatt, bkg_trans, problem) for a `bg<N>` sample within one config.

    Prefer the bkg<N> run at the sample's temperature token; otherwise the only
    bkg<N> run in the config. The newest run wins among equals, as for
    transmissions. An unresolved pointer returns a problem string, never a guess.
    """
    t = _TEMP_SUFFIX_RE.search(sample_name)
    temp = t.group(1).upper() if t else None

    def choose(cands: list["ClassifiedRun"]) -> tuple[str, str]:
        numbered = [r for r in cands if (m := _BKG_ID_RE.search(r.sample_name)) and int(m.group(1)) == n]
        if not numbered:
            return "", "absent"
        def temp_of(r):
            m = _TEMP_SUFFIX_RE.search(r.sample_name)
            return m.group(1).upper() if m else None
        same = [r for r in numbered if temp_of(r) == temp]
        if same:
            return str(max(r.run_number for r in same)), ""
        temps = {temp_of(r) for r in numbered}
        if len(temps) == 1:
            return str(max(r.run_number for r in numbered)), ""
        return "", f"bkg{n} measured at {sorted(str(x) for x in temps)}, none at {temp}"

    s, s_problem = choose(bkg_scatt)
    tr, _ = choose(bkg_trans)
    if s_problem == "absent":
        return "", "", f"no bkg{n} run in this configuration"
    return s, tr, s_problem


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
        1. Background keywords checked FIRST (emptycell/emptyticell/ti-cell/banjo/emptycup/bkg)
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


def _match_base(sample_name: str) -> str:
    """Normalization key for transmission matching.

    Strips a trailing temperature (``_90C``) and any sample-displacement token
    (``_d0``, ``_d16``) so one transmission measured for a sample series matches
    every displacement of it. A series like ``S-poly_d0``, ``S-poly_d2`` … all
    reduce to ``poly`` and find the single ``T-poly`` transmission.

    Only the displacement convention ``_d<number>`` is stripped; ``_d2o`` and
    other non-numeric ``d`` tokens are left alone (the ``(?=_|$)`` lookahead
    requires the digits to end the token).

    A rheo-SANS shear-rate token (``_0.1shear``, ``_1000shear``,
    ``_0shear-return``) is stripped the same way: the transmission is measured
    once at rest (``T-CTAB 1,3_0shear``) and serves every shear rate of that
    sample. Other tokens — the shear plane ``1,3`` / ``2,3`` — are kept, so a
    plane only ever matches its own transmission.
    """
    s = re.sub(r"_?\d{2,3}C$", "", sample_name, flags=re.IGNORECASE)  # temperature
    s = re.sub(r"_d\d+(?=_|$)", "", s, flags=re.IGNORECASE)           # displacement
    s = re.sub(r"_\d+(?:[.p]\d+)?shear(?:-[a-z0-9]+)*(?=_|$)", "", s,
               flags=re.IGNORECASE)                                   # shear rate
    s = re.sub(r"__+", "_", s).strip("_")
    return s.lower()


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

    # Strip detector/wavelength/frequency config: "4m 10A", "2.5m 2.5a",
    # "4m 10a 60Hz", plus a frame-skipping mode suffix that may be glued to the
    # wavelength ("4m 2.5afs") or spaced ("4m 2.5a fs"). Without consuming "fs"
    # a transmission titled "T-porsil 4m 2.5afs" would parse to "porsil_fs" and
    # never match the sample "S-porsil 4m 2.5a" → "porsil" (IPTS-38151).
    # Handles various orderings and is non-greedy (stops at next token boundary).
    s = re.sub(
        r"\s*\d+\.?\d*\s*m\s+\d+\.?\d*\s*[aA]"   # distance + wavelength: "4m 2.5a"
        r"(?:\s*fs)?"                            # frame-skipping, attached or spaced
        r"(?:\s*\d+\s*[hH]z)?"                   # frequency: "60Hz" / "30hz"
        r"(?:\s*fs)?",                           # fs may also trail the frequency
        " ", s, flags=re.IGNORECASE)
    # The same written compactly, as a word of its own: "4m2.5a", "8m10a",
    # "2p5m2p5a". Left in, it doubled into the output name
    # (CTAB_1,3_0shear_4m2.5a_4m2.5a_Iq.dat) and split one sample into one
    # stitch group per configuration (IPTS-37681).
    s = re.sub(_CFG_WORD_RE, " ", s)

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


# A configuration token in a name says nothing about which run belongs to
# which sample — every candidate in a config shares the configuration. Names
# from sessions matched before v0.47.2 can still carry one ("CTAB_1,3_4m2.5a").
_CFG_TOKEN_RE = re.compile(_CFG_BODY + r"$", re.IGNORECASE)


def strip_config_tokens(name: str) -> str:
    """`name` without any `_`-delimited configuration token (`4m2.5a`, `8m10a30hz`)."""
    kept = [t for t in name.split("_") if not (t and _CFG_TOKEN_RE.match(t))]
    return "_".join(kept) or name


def _name_tokens(name: str) -> set[str]:
    return {t for t in re.split(r"[_\s]+", name.lower())
            if t and not _CFG_TOKEN_RE.match(t)}


def _pick_by_shared_token(sample_name: str,
                          cands: list[ClassifiedRun]) -> ClassifiedRun | None:
    """Among several empty beams / backgrounds of one config, the one the sample names.

    A candidate's *distinguishing* tokens are those not common to every
    candidate. Pick the candidate whose distinguishing tokens the sample's name
    shares — `T-empty beam 2,3` for `S-CTAB 2,3_10shear` (rheo-SANS: the 1,3
    and 2,3 shear planes are different beam paths through the cell, so each has
    its own empty beam and empty cup). Repeats of one name count as one and the
    newest run wins. None when no candidate, or more than one, is named — the
    caller keeps its config default, so a title without such a token matches
    exactly as before.
    """
    if len(cands) < 2:
        return None
    toks = [_name_tokens(c.sample_name) for c in cands]
    common = set.intersection(*toks)
    mine = _name_tokens(sample_name)
    hits = [c for c, t in zip(cands, toks) if (t - common) & mine]
    if len({c.sample_name.lower() for c in hits}) != 1:
        return None
    return max(hits, key=lambda c: c.run_number)


def match_runs(catalog: pd.DataFrame, ipts: int = 0,
               title_tokens: bool = True) -> tuple[WorkingTable, list[str]]:
    """Auto-match runs from a catalog into a working table.

    Returns (table, warnings) where warnings is a list of human-readable
    warning strings (e.g. multiple empty beams per config).

    - ALL scattering runs in the table (including bkg/empty).
    - Transmission matched for EVERY scattering run by sample name.
    - Bkg/empty scattering runs get empty beam as their own background.
    - Config = (distance, wavelength, frequency).
    - With ``title_tokens`` (default), a sample titled with ``bg<N>`` gets the
      ``bkg<N>`` background of its config instead of the config default
      (BKG-04), and ``th<X>mm`` sets the row thickness (TBL-08). Titles without
      those tokens are matched exactly as before.
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

        # Rows whose empty beam / background came from the config default while
        # the config had several to choose from (CAT-03, CAT-04). Warned after
        # the rows are built, because a shared title token (CAT-09) may have
        # made the choice for every row.
        empty_defaulted = False
        bkg_defaulted = False
        token_picks: dict[str, set[str]] = {"empty beam": set(), "background": set()}

        default_empty = str(empty_trans_runs[0].run_number) if empty_trans_runs else ""
        default_bkg_scatt = str(bkg_scatt_runs[0].run_number) if bkg_scatt_runs else ""
        default_bkg_trans = str(bkg_trans_runs[0].run_number) if bkg_trans_runs else ""

        # Transmission lookup: ALL transmission-type runs indexed by sample name.
        # This ensures bkg/empty scattering runs find their T-banjo/T-empty matches.
        trans_lookup: dict[str, str] = {}
        trans_lookup_base: dict[str, str] = {}  # fallback: temperature/displacement stripped
        for r in runs:
            if r.run_type in ("transmission", "bkg_trans", "empty_trans"):
                trans_lookup[r.sample_name.lower()] = str(r.run_number)
                trans_lookup_base[_match_base(r.sample_name)] = str(r.run_number)

        # Last-resort fallback: a sample series measured at several displacements
        # (S-…_d0, _d2, …) shares ONE transmission. If this config has exactly one
        # plain transmission run, an unmatched normal scattering row can only mean
        # that run — assign it, but record it so the user can see it was matched by
        # configuration rather than by name.
        sole_trans = [r for r in runs if r.run_type == "transmission"]
        sole_trans_run = str(sole_trans[0].run_number) if len(sole_trans) == 1 else ""
        by_config_assigned: list[str] = []

        for s in all_scattering:
            trans_run = trans_lookup.get(s.sample_name.lower(), "")
            matched_by = "name"
            if not trans_run:
                # Fallback: strip temperature and displacement, match on base name
                trans_run = trans_lookup_base.get(_match_base(s.sample_name), "")
                if trans_run:
                    matched_by = "base"

            row_empty = default_empty
            if len(empty_trans_runs) > 1:
                pick = _pick_by_shared_token(s.sample_name, empty_trans_runs) if title_tokens else None
                if pick is not None:
                    row_empty = str(pick.run_number)
                    token_picks["empty beam"].add(f"{pick.run_number} ({pick.sample_name})")
                else:
                    empty_defaulted = True

            if s.is_background or s.is_empty:
                # Background-cell and empty-beam rows don't get an auto-assigned
                # background — empty-beam is a calibration measurement, not a
                # background reference. User can /set <row> bkg <run> manually
                # if subtraction is desired for a specific bkg cell.
                row_bkg_scatt = ""
                row_bkg_trans = ""
            else:
                if not trans_run and sole_trans_run:
                    trans_run = sole_trans_run
                    matched_by = "config"
                    by_config_assigned.append(s.sample_name)
                row_bkg_scatt = default_bkg_scatt
                row_bkg_trans = default_bkg_trans
                n_ptr = background_pointer(s.sample_name) if title_tokens else None
                if n_ptr is None and len(bkg_scatt_runs) > 1:
                    pick = _pick_by_shared_token(s.sample_name, bkg_scatt_runs) if title_tokens else None
                    if pick is not None:
                        row_bkg_scatt = str(pick.run_number)
                        same = [r for r in bkg_trans_runs
                                if r.sample_name.lower() == pick.sample_name.lower()]
                        t_pick = (max(same, key=lambda r: r.run_number) if same
                                  else _pick_by_shared_token(s.sample_name, bkg_trans_runs))
                        if t_pick is not None:
                            row_bkg_trans = str(t_pick.run_number)
                        token_picks["background"].add(f"{pick.run_number} ({pick.sample_name})")
                    else:
                        bkg_defaulted = True
                if n_ptr is not None:
                    b_s, b_t, problem = _pick_numbered_background(
                        n_ptr, s.sample_name, bkg_scatt_runs, bkg_trans_runs)
                    if problem:
                        warnings.append(
                            f"[{cfg_label}] {s.sample_name}: title asks for bkg{n_ptr} but "
                            f"{problem}; using the config default {default_bkg_scatt or '(none)'}.\n"
                            f"  Fix the title with /retitle, or /set <row> bkg <run>."
                        )
                    else:
                        row_bkg_scatt, row_bkg_trans = b_s, b_t

            row = WorkingTableRow(
                index=0,
                scattering_run=str(s.run_number),
                sample_name=s.sample_name,
                transmission_run=trans_run,
                background_scatt=row_bkg_scatt,
                background_trans=row_bkg_trans,
                empty_beam=row_empty,
                detector_distance=s.detector_distance,
                wavelength=s.wavelength,
                frequency=s.frequency,
            )
            th = title_thickness_cm(s.sample_name) if title_tokens else None
            if th is not None:
                row.thickness = th
            table.add_row(row)

        if empty_defaulted:
            run_list = ", ".join(f"{r.run_number} ({r.title[:25]})" for r in empty_trans_runs)
            warnings.append(
                f"[{cfg_label}] {len(empty_trans_runs)} empty beam runs found: {run_list}\n"
                f"  Using {empty_trans_runs[0].run_number} as default. "
                f"Use /set <row> emp <run> to override."
            )
        if bkg_defaulted:
            run_list = ", ".join(f"{r.run_number} ({r.title[:25]})" for r in bkg_scatt_runs)
            warnings.append(
                f"[{cfg_label}] {len(bkg_scatt_runs)} background scatt runs found: {run_list}\n"
                f"  Using {bkg_scatt_runs[0].run_number} as default. "
                f"Use /assign bkg <sample> to override."
            )
        for role, picked in token_picks.items():
            if picked:
                warnings.append(
                    f"[{cfg_label}] {role} chosen per row by the title token the sample "
                    f"shares with it: {', '.join(sorted(picked))}.\n"
                    f"  Verify with /show table; /matchruns --no-title-tokens uses the first one."
                )

        if by_config_assigned:
            n = len(by_config_assigned)
            warnings.append(
                f"[{cfg_label}] transmission {sole_trans_run} matched to {n} row(s) "
                f"by configuration (one transmission in this config, names did not "
                f"match): {', '.join(by_config_assigned)}.\n"
                f"  Verify, or use /set <row> trans <run> to override."
            )

    return table, warnings


def merge_new_runs(
    existing_table: WorkingTable,
    fresh_catalog: pd.DataFrame,
    ipts: int = 0,
    title_tokens: bool = True,
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
    fresh_table, fresh_warnings = match_runs(fresh_catalog, ipts=ipts, title_tokens=title_tokens)

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
                # A background named by the title's bg<N> token (BKG-04) is the
                # proposal's choice for this sample; the config's inherited
                # background must not overwrite it.
                named_bkg = (title_tokens and background_pointer(row.sample_name) is not None
                             and row.background_scatt)
                if not named_bkg:
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

    # Reconcile preserved rows against runs now reclassified to 'ignore'. --update
    # keeps existing assignments verbatim, so a transmission/background/empty that
    # the user has since marked ignore (e.g. an old transmission remeasured after a
    # bad wavelength) would otherwise keep being used. Drop rows whose scattering
    # run is now ignored, and re-match any ignored trans/bkg/empty from the fresh
    # table (falling back to blank).
    fresh_by_scatt = {r.scattering_run: r for r in fresh_table.rows}
    run_fields = ("transmission_run", "background_scatt", "background_trans", "empty_beam")

    ignored_runs: set[str] = set()
    if "run_class" in fresh_catalog.columns and "run_number" in fresh_catalog.columns:
        for _, r in fresh_catalog.iterrows():
            if str(r.get("run_class", "")) == "ignore":
                ignored_runs.add(str(r["run_number"]))

    if ignored_runs:
        def _uses(value: str) -> bool:
            return any(p.strip() in ignored_runs
                       for p in str(value or "").replace("+", ",").split(","))

        removed = [row.index for row in existing_table.rows if _uses(row.scattering_run)]
        for idx in sorted(removed, reverse=True):
            existing_table.remove_row(idx)
        if removed:
            warnings.append(
                f"Removed {len(removed)} row(s) whose scattering run was reclassified "
                f"to ignore."
            )

        n_fixed = 0
        for row in existing_table.rows:
            fresh = fresh_by_scatt.get(row.scattering_run)
            for f in run_fields:
                if _uses(getattr(row, f, "")):
                    row.set_field(f, getattr(fresh, f, "") if fresh else "")  # done → modified
                    n_fixed += 1
        if n_fixed:
            warnings.append(
                f"Re-matched {n_fixed} assignment(s) that pointed at now-ignored runs; "
                f"affected rows were marked 'modified' for re-reduction."
            )

    # Back-fill assignments that only became available since the first match. Common
    # case: you match while collecting (scattering done, transmission not yet), then
    # measure the transmission later — it gets a HIGHER run number and appears in the
    # fresh catalog. --update preserves existing rows verbatim, so an EMPTY field
    # would otherwise never fill. Copy the fresh match's value into any field that is
    # still blank (never overwriting a value already set — those may be user edits).
    n_filled = 0
    for row in existing_table.rows:
        fresh = fresh_by_scatt.get(row.scattering_run)
        if fresh is None:
            continue
        for f in run_fields:
            if not getattr(row, f, "") and getattr(fresh, f, ""):
                row.set_field(f, getattr(fresh, f))  # done → modified
                n_filled += 1
    if n_filled:
        warnings.append(
            f"Filled {n_filled} newly-available assignment(s) on existing rows "
            f"(e.g. a transmission measured after the first match); affected rows "
            f"were marked 'modified' for re-reduction."
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
