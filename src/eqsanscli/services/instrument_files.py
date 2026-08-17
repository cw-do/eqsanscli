"""Run-aware discovery of instrument calibration files from the machine-physics folders.

Each accelerator cycle gets a folder under
``/SNS/EQSANS/shared/NeXusFiles/EQSANS`` named ``<year><A|B>_mp`` holding that
cycle's calibration set: dark current, sensitivity (flood) maps per detector
distance, the beam flux spectrum, and — since 2026A — AgBe geometry/timing
calibration (``detoffset``, ``scalecomp``, ``samoffset``).

This module answers one question: *for a data run at a given detector
distance, which calibration files and values apply?*

**Why the folder and not the web page.** The machine-physics summary page
(https://cw-do.github.io/eqsans_mp/) is *generated from* these folders by
``<mp_root>/doc/generate.py``, which writes ``doc/data.js`` and pushes it to
GitHub Pages. The page is a derived view that only refreshes when someone
republishes it, so the folder is the source of truth — and reduction needs
filesystem paths anyway, which only mean something on the mounted share. The
naming rules below deliberately mirror ``doc/generate.py``; if that generator's
rules change, change these too.

**Selection policy — cycle-coherent.** Pick the newest cycle whose calibration
campaign started at or before the data run (its *anchor run*, the lowest
dark/flood run in the folder), then take the whole set from that cycle. A data
run can land between a cycle's dark run and its flood runs; taking the cycle as
a unit avoids pairing this cycle's dark with last cycle's floods. Falling back
to an earlier cycle happens only when the chosen one lacks what is needed.
Anchor runs are strictly increasing across every cycle from 2011B to 2026B, so
ordering by run number and ordering by cycle agree.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

logger = logging.getLogger(__name__)

DEFAULT_MP_ROOT = "/SNS/EQSANS/shared/NeXusFiles/EQSANS"

#: Environment override, mainly for tests against a synthetic tree.
MP_ROOT_ENV = "EQSANSCLI_MP_ROOT"

_CYCLE_RE = re.compile(r"^(\d{4})([AB])_mp$")

# Distance tokens in sensitivity file names -> metres. ORDER MATTERS: "2o5m"
# must be tested before "5m", or "Sensitivity_..._2o5m_..." reads as 5 m.
_DIST_TOKENS: tuple[tuple[str, float], ...] = (
    ("1300mm", 1.3), ("2500mm", 2.5),
    ("1o3m", 1.3), ("2o5m", 2.5), ("2o0m", 2.0),
    ("4m", 4.0), ("5m", 5.0), ("8m", 8.0), ("2m", 2.0),
)

#: Preferred flood variant. Every cycle since 2026A produces only this one;
#: 2025B also carries 5mmPMMA maps with *higher* run numbers, which a purely
#: run-driven pick would wrongly prefer.
DEFAULT_VARIANT = "thinPMMA"

#: Flux spectra only started living in the cycle folders in 2026A (2013B has a
#: stray one). Without a limit, a 2024 run would reach back to 2013B — worse
#: than leaving the existing value alone.
FLUX_FALLBACK_CYCLES = 1

# Flattened, lowercased config keys this module owns (see config_manager).
PARAM_SENSITIVITY = "sensitivityfilename"
PARAM_DARK = "darkfilename"
PARAM_FLUX = "beamfluxfilename"
PARAM_DETOFFSET = "detectoroffset"
PARAM_SAMPLEOFFSET = "sampleoffset"
PARAM_SCALECOMP = "scalecomponents.detector1"

#: Every parameter this module may write, in report order.
MANAGED_PARAMS: tuple[str, ...] = (
    PARAM_SENSITIVITY, PARAM_DARK, PARAM_FLUX,
    PARAM_DETOFFSET, PARAM_SCALECOMP, PARAM_SAMPLEOFFSET,
)

#: Short labels for display.
PARAM_LABELS = {
    PARAM_SENSITIVITY: "sensitivity",
    PARAM_DARK: "dark current",
    PARAM_FLUX: "beam flux",
    PARAM_DETOFFSET: "detector offset",
    PARAM_SCALECOMP: "scale components",
    PARAM_SAMPLEOFFSET: "sample offset",
}


def mp_root() -> str:
    """The machine-physics root, overridable via ``EQSANSCLI_MP_ROOT``."""
    return os.environ.get(MP_ROOT_ENV) or DEFAULT_MP_ROOT


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class DarkFile:
    path: str
    run: int
    size: int

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


@dataclass(frozen=True)
class SensitivityFile:
    path: str
    run: int
    distance: float
    tag: str
    variant: str
    plain: bool  # tag appears as "_<tag>_<run>" — undecorated (4m, not 4mSM)

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


@dataclass(frozen=True)
class FluxFile:
    path: str

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


@dataclass(frozen=True)
class AgBeCalibration:
    detoffset: Optional[float] = None
    scalecomp: Optional[list[float]] = None
    samoffset: Optional[float] = None
    scale_y: Optional[float] = None
    scale_all: Optional[float] = None
    source: str = ""
    partial: bool = False

    @property
    def usable(self) -> bool:
        return self.detoffset is not None or self.scalecomp is not None


@dataclass
class Cycle:
    """One ``<year><A|B>_mp`` folder."""

    cycle_id: str  # "2026B"
    path: str
    darks: list[DarkFile] = field(default_factory=list)
    sensitivities: list[SensitivityFile] = field(default_factory=list)
    flux: list[FluxFile] = field(default_factory=list)

    @property
    def anchor_run(self) -> int:
        """Lowest calibration run in the folder — when this cycle takes effect."""
        runs = [d.run for d in self.darks] + [s.run for s in self.sensitivities]
        return min(runs) if runs else 0

    @property
    def agbe(self) -> Optional[AgBeCalibration]:
        """AgBe calibration, parsed lazily (it needs a directory walk)."""
        return _agbe_for_cycle(self.path)

    def sensitivity_distances(self) -> list[float]:
        return sorted({s.distance for s in self.sensitivities})


@dataclass(frozen=True)
class ResolvedParam:
    """One resolved config parameter, with where it came from."""

    param: str
    value: object
    cycle_id: str
    source: str  # absolute path the value came from
    note: str = ""  # e.g. "8.0 m uses the 4 m flood"

    @property
    def label(self) -> str:
        return PARAM_LABELS.get(self.param, self.param)


@dataclass
class Resolution:
    """Everything resolved for one (run, distance) pair."""

    run: int
    distance: float
    cycle_id: Optional[str] = None
    params: dict[str, ResolvedParam] = field(default_factory=dict)
    missing: list[str] = field(default_factory=list)  # human-readable reasons
    notes: list[str] = field(default_factory=list)

    @property
    def values(self) -> dict[str, object]:
        return {p: r.value for p, r in self.params.items()}

    def cycles_used(self) -> list[str]:
        return sorted({r.cycle_id for r in self.params.values() if r.cycle_id})


# --------------------------------------------------------------------------
# Scanning
# --------------------------------------------------------------------------

def _run_from_name(name: str) -> Optional[int]:
    """Last 4-7 digit group in a file name, ignoring extensions.

    Matches ``doc/generate.py``'s ``run_number``. Not anchored to the end
    because older files carry decorations after the run
    (``..._113515_mantid.nxs``, ``..._56036_2_event.nxs``).
    """
    stem = os.path.basename(name).split(".")[0]
    nums = re.findall(r"(\d{4,7})", stem)
    return int(nums[-1]) if nums else None


def _distance_of(name: str) -> tuple[Optional[float], str]:
    low = name.lower()
    for tok, metres in _DIST_TOKENS:
        if tok in low:
            return metres, tok
    return None, ""


def _variant_of(name: str) -> str:
    m = re.match(r"sensitivity[_-]?patched[_-]([A-Za-z0-9]+?)[_-]", name, re.I)
    return m.group(1) if m else ""


def _is_dark_name(low: str) -> bool:
    if not low.startswith("eqsans_"):
        return False
    if "sensitivity" in low:
        return False
    return low.endswith(".nxs.h5") or low.endswith("_event.nxs") or low.endswith(".nxs")


def _scan_cycle(cycle_id: str, cycle_dir: str) -> Cycle:
    cycle = Cycle(cycle_id=cycle_id, path=cycle_dir)
    try:
        names = sorted(os.listdir(cycle_dir))
    except OSError as exc:
        logger.warning("Cannot list %s: %s", cycle_dir, exc)
        return cycle

    for name in names:
        low = name.lower()
        full = os.path.join(cycle_dir, name)
        if low.startswith("sensitivity") and low.endswith(".nxs"):
            run = _run_from_name(name)
            distance, tag = _distance_of(name)
            if run is None or distance is None:
                # Pre-2022 files without a parseable distance token are not
                # candidates; they stay visible on the summary page instead.
                continue
            plain = re.search(rf"[_-]{re.escape(tag)}[_-]\d", low) is not None
            cycle.sensitivities.append(SensitivityFile(
                path=full, run=run, distance=distance, tag=tag,
                variant=_variant_of(name), plain=plain,
            ))
        elif _is_dark_name(low):
            run = _run_from_name(name)
            if run is None:
                continue
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            cycle.darks.append(DarkFile(path=full, run=run, size=size))
        elif "flux" in low and low.endswith(".txt"):
            # Top level only. final_flux/, flux_4m/ etc. are working areas;
            # what sits at the top of the cycle folder is what it publishes.
            cycle.flux.append(FluxFile(path=full))

    return cycle


# Cache keyed on (root, mtime signature of the root + cycle dirs).
_SCAN_CACHE: dict[tuple, list[Cycle]] = {}
_AGBE_CACHE: dict[tuple[str, float], Optional[AgBeCalibration]] = {}


def _signature(root: str, cycle_dirs: Sequence[str]) -> tuple:
    def mtime(p: str) -> float:
        try:
            return os.path.getmtime(p)
        except OSError:
            return 0.0
    return (root, mtime(root)) + tuple((d, mtime(d)) for d in cycle_dirs)


def scan_cycles(root: Optional[str] = None, *, use_cache: bool = True) -> list[Cycle]:
    """All cycle folders under `root`, newest anchor run first.

    Cached on the mtimes of the root and each cycle folder, so a new file
    dropped into a cycle invalidates the cache by itself.
    """
    root = root or mp_root()
    try:
        entries = sorted(os.listdir(root))
    except OSError as exc:
        logger.warning("Machine-physics root unavailable (%s): %s", root, exc)
        return []

    pairs = [(m.group(1) + m.group(2), os.path.join(root, e))
             for e in entries for m in [_CYCLE_RE.match(e)] if m]
    pairs = [(cid, d) for cid, d in pairs if os.path.isdir(d)]

    key = _signature(root, [d for _, d in pairs])
    if use_cache and key in _SCAN_CACHE:
        return _SCAN_CACHE[key]

    cycles = [_scan_cycle(cid, d) for cid, d in pairs]
    cycles = [c for c in cycles if c.anchor_run]
    cycles.sort(key=lambda c: c.anchor_run, reverse=True)
    if use_cache:
        _SCAN_CACHE.clear()
        _SCAN_CACHE[key] = cycles
    return cycles


def clear_cache() -> None:
    """Drop cached scans (used by /instrument apply --rescan and by tests)."""
    _SCAN_CACHE.clear()
    _AGBE_CACHE.clear()


# --------------------------------------------------------------------------
# AgBe calibration
# --------------------------------------------------------------------------

_AGBE_REPORT_KEYS = {
    "scale_y": re.compile(r"scale_y\s*:?\s*=?\s*([0-9.]+)", re.I),
    "scale_all": re.compile(r"scale_all\s*:?\s*=?\s*([0-9.]+)", re.I),
    "detoffset": re.compile(r"detoffset\s*:?\s*=?\s*([0-9.]+)", re.I),
    "samoffset": re.compile(r"samoffset\s*:?\s*=?\s*([0-9.]+)", re.I),
}


def _parse_report(path: str) -> dict:
    try:
        with open(path, errors="replace") as fh:
            text = fh.read()
    except OSError:
        return {}
    vals: dict = {}
    for key, rx in _AGBE_REPORT_KEYS.items():
        m = rx.search(text)
        if m:
            vals[key] = float(m.group(1))
    m = re.search(r"scalecomp\s*=\s*\[([^\]]+)\]", text)
    if m:
        try:
            vals["scalecomp"] = [float(x) for x in m.group(1).split(",")]
        except ValueError:
            pass
    return vals


def _parse_checkpoint(path: str) -> dict:
    try:
        with open(path, errors="replace") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return {}
    res = data.get("results") or {}
    vals: dict = {}
    for k in ("scale_y", "scale_all", "detoffset"):
        v = res.get(k)
        if isinstance(v, (int, float)):
            vals[k] = float(v)
    if isinstance(res.get("scalecomp"), list):
        try:
            vals["scalecomp"] = [float(x) for x in res["scalecomp"]]
        except (TypeError, ValueError):
            pass
    vals["partial"] = len(data.get("completed_steps") or []) < 3
    return vals


def _agbe_for_cycle(cycle_dir: str) -> Optional[AgBeCalibration]:
    try:
        stamp = os.path.getmtime(cycle_dir)
    except OSError:
        stamp = 0.0
    ck = (cycle_dir, stamp)
    if ck in _AGBE_CACHE:
        return _AGBE_CACHE[ck]

    checkpoints: list[str] = []
    reports: list[str] = []
    for dirpath, dirnames, filenames in os.walk(cycle_dir):
        # Don't descend into the parameter-scan trees — thousands of files.
        dirnames[:] = [d for d in dirnames
                       if not d.startswith("scaleall_")
                       and not d.startswith("scale_detoffset")
                       and d not in ("__pycache__", ".git", "legacy")]
        for f in filenames:
            if f == "checkpoint.json":
                checkpoints.append(os.path.join(dirpath, f))
            elif f == "calibration_report.txt":
                reports.append(os.path.join(dirpath, f))

    result: Optional[AgBeCalibration] = None
    # checkpoint.json is the machine-readable record; the report next to it
    # carries samoffset, which the checkpoint does not.
    for ckpt in sorted(checkpoints, key=os.path.getmtime, reverse=True):
        vals = _parse_checkpoint(ckpt)
        if not vals.get("detoffset") and not vals.get("scalecomp"):
            continue
        sibling = os.path.join(os.path.dirname(ckpt), "calibration_report.txt")
        if os.path.exists(sibling):
            for k, v in _parse_report(sibling).items():
                vals.setdefault(k, v)
        result = AgBeCalibration(
            detoffset=vals.get("detoffset"), scalecomp=vals.get("scalecomp"),
            samoffset=vals.get("samoffset"), scale_y=vals.get("scale_y"),
            scale_all=vals.get("scale_all"), source=ckpt,
            partial=bool(vals.get("partial")),
        )
        break

    if result is None:
        for rep in sorted(reports, key=os.path.getmtime, reverse=True):
            vals = _parse_report(rep)
            if not vals.get("detoffset") and not vals.get("scalecomp"):
                continue
            result = AgBeCalibration(
                detoffset=vals.get("detoffset"), scalecomp=vals.get("scalecomp"),
                samoffset=vals.get("samoffset"), scale_y=vals.get("scale_y"),
                scale_all=vals.get("scale_all"), source=rep,
            )
            break

    _AGBE_CACHE[ck] = result
    return result


# --------------------------------------------------------------------------
# Selection
# --------------------------------------------------------------------------

def flood_distance_for(distance: float, available: Iterable[float]) -> Optional[float]:
    """Map a measured detector distance onto an available flood distance.

    Clamp into the available range, then take the nearest (ties → the larger).
    So 8 m and 5 m use the 4 m flood, 1.3 m uses 1.3 m, and 2.0 m uses 2.5 m.
    """
    tags = sorted(set(available))
    if not tags:
        return None
    clamped = min(max(distance, tags[0]), tags[-1])
    return min(tags, key=lambda t: (abs(t - clamped), -t))


def _pick_dark(cycle: Cycle) -> Optional[DarkFile]:
    if not cycle.darks:
        return None
    newest = max(d.run for d in cycle.darks)
    same = [d for d in cycle.darks if d.run == newest]
    # Dark current is a long measurement; with several at the same run the
    # biggest file is the real one.
    return max(same, key=lambda d: d.size)


def _pick_sensitivity(
    cycle: Cycle, target_distance: float, variant_pref: str,
) -> Optional[SensitivityFile]:
    cands = [s for s in cycle.sensitivities if s.distance == target_distance]
    if not cands:
        return None
    # Preferred variant first, then undecorated tag (4m over 4mSM), then the
    # newest run within the cycle (2022A holds four flood generations).
    return max(cands, key=lambda s: (
        s.variant.lower() == variant_pref.lower(), s.plain, s.run,
    ))


def _pick_flux(cycle: Cycle) -> Optional[FluxFile]:
    if not cycle.flux:
        return None
    # Deterministic: newest by name, which sorts the cycle's own naming
    # (bl6_flux_<cycle>_<month>_rebinned.txt) sensibly.
    return sorted(cycle.flux, key=lambda f: f.name)[-1]


def select_cycle(run: int, cycles: Sequence[Cycle]) -> Optional[Cycle]:
    """Newest cycle whose calibration campaign started at or before `run`."""
    eligible = [c for c in cycles if c.anchor_run and c.anchor_run <= run]
    if not eligible:
        return None
    return max(eligible, key=lambda c: c.anchor_run)


def resolve_for_run(
    run: int,
    distance: float,
    *,
    root: Optional[str] = None,
    cycles: Optional[Sequence[Cycle]] = None,
    pin_cycle: Optional[str] = None,
    variant_pref: str = DEFAULT_VARIANT,
) -> Resolution:
    """Resolve the calibration set for a data run at `distance` metres.

    `pin_cycle` forces a specific cycle id ("2026A") regardless of run number,
    for reproducing an earlier reduction.
    """
    all_cycles = list(cycles if cycles is not None else scan_cycles(root))
    res = Resolution(run=run, distance=distance)

    if not all_cycles:
        res.missing.append(
            f"No cycle folders found under {root or mp_root()} — "
            f"instrument files left unchanged."
        )
        return res

    ordered = sorted(all_cycles, key=lambda c: c.anchor_run, reverse=True)

    if pin_cycle:
        pinned = next((c for c in ordered if c.cycle_id.lower() == pin_cycle.lower()), None)
        if pinned is None:
            res.missing.append(
                f"Pinned cycle '{pin_cycle}' not found. Available: "
                f"{', '.join(c.cycle_id for c in ordered)}"
            )
            return res
        start = pinned
        res.notes.append(f"Pinned to cycle {pinned.cycle_id} (run number ignored).")
    else:
        start = select_cycle(run, ordered)
        if start is None:
            oldest = min(ordered, key=lambda c: c.anchor_run)
            res.missing.append(
                f"Run {run} predates every calibration cycle "
                f"(earliest is {oldest.cycle_id}, run {oldest.anchor_run}) — "
                f"instrument files left unchanged."
            )
            return res

    res.cycle_id = start.cycle_id
    start_index = ordered.index(start)
    # Cycles to fall back through, oldest-ward from the chosen one.
    chain = ordered[start_index:]

    # --- dark current ---
    for i, cycle in enumerate(chain):
        dark = _pick_dark(cycle)
        if dark:
            res.params[PARAM_DARK] = ResolvedParam(
                param=PARAM_DARK, value=dark.path, cycle_id=cycle.cycle_id,
                source=dark.path,
                note="" if i == 0 else f"{start.cycle_id} has none; used {cycle.cycle_id}",
            )
            break
    else:
        res.missing.append("No dark current file found in any cycle.")

    # --- sensitivity (flood) ---
    available = sorted({s.distance for c in chain for s in c.sensitivities})
    target = flood_distance_for(distance, available)
    if target is None:
        res.missing.append("No sensitivity files found in any cycle.")
    else:
        for i, cycle in enumerate(chain):
            sens = _pick_sensitivity(cycle, target, variant_pref)
            if sens:
                note_bits = []
                if abs(target - distance) > 1e-6:
                    note_bits.append(f"{_fmt_m(distance)} uses the {_fmt_m(target)} flood")
                if i:
                    note_bits.append(f"{start.cycle_id} has no {sens.tag}; used {cycle.cycle_id}")
                if sens.variant and sens.variant.lower() != variant_pref.lower():
                    note_bits.append(f"variant {sens.variant} ({variant_pref} not available)")
                res.params[PARAM_SENSITIVITY] = ResolvedParam(
                    param=PARAM_SENSITIVITY, value=sens.path, cycle_id=cycle.cycle_id,
                    source=sens.path, note="; ".join(note_bits),
                )
                break
        else:
            res.missing.append(
                f"No sensitivity file for {_fmt_m(target)} in any cycle at or before {run}."
            )

    # --- beam flux ---
    for i, cycle in enumerate(chain[:FLUX_FALLBACK_CYCLES + 1]):
        flux = _pick_flux(cycle)
        if flux:
            res.params[PARAM_FLUX] = ResolvedParam(
                param=PARAM_FLUX, value=flux.path, cycle_id=cycle.cycle_id,
                source=flux.path,
                note="" if i == 0 else f"{start.cycle_id} has none; used {cycle.cycle_id}",
            )
            break
    else:
        res.missing.append(
            f"No beam flux file in {start.cycle_id} or the cycle before it — "
            f"existing value kept (flux files only appear in recent cycles)."
        )

    # --- AgBe calibration ---
    for i, cycle in enumerate(chain):
        agbe = cycle.agbe
        if agbe is None or not agbe.usable:
            continue
        note = "" if i == 0 else f"{start.cycle_id} has none; used {cycle.cycle_id}"
        if agbe.partial:
            note = "; ".join(filter(None, [note, "calibration incomplete"]))
        if agbe.detoffset is not None:
            res.params[PARAM_DETOFFSET] = ResolvedParam(
                param=PARAM_DETOFFSET, value=float(agbe.detoffset),
                cycle_id=cycle.cycle_id, source=agbe.source, note=note,
            )
        if agbe.scalecomp:
            res.params[PARAM_SCALECOMP] = ResolvedParam(
                param=PARAM_SCALECOMP, value=list(agbe.scalecomp),
                cycle_id=cycle.cycle_id, source=agbe.source, note=note,
            )
        if agbe.samoffset is not None:
            res.params[PARAM_SAMPLEOFFSET] = ResolvedParam(
                param=PARAM_SAMPLEOFFSET, value=float(agbe.samoffset),
                cycle_id=cycle.cycle_id, source=agbe.source, note=note,
            )
        break
    else:
        res.missing.append(
            "No AgBe calibration at or before this run — detector offset, scale "
            "components and sample offset left unchanged."
        )

    # A cycle-coherent set can include a file measured just after the data run
    # (e.g. run 186199 with floods 186200-186202). Harmless — a flood
    # characterises the detector, not the run — but worth recording.
    later = [
        f"{r.label} run is {_run_from_name(r.source)} (> data run {run})"
        for r in res.params.values()
        if r.param in (PARAM_SENSITIVITY, PARAM_DARK)
        and (_run_from_name(r.source) or 0) > run
    ]
    res.notes.extend(later)

    return res


def _fmt_m(value: float) -> str:
    return f"{value:g} m"


# --------------------------------------------------------------------------
# Applying a resolution to a config
# --------------------------------------------------------------------------

@dataclass
class ApplyOutcome:
    """What happened when a resolution met an existing config."""

    config_id: str
    resolution: Resolution
    written: dict[str, object] = field(default_factory=dict)
    unchanged: list[str] = field(default_factory=list)
    kept_user: dict[str, object] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        return bool(self.written)


def _same(a: object, b: object) -> bool:
    """Value equality that tolerates int/float and list/tuple mixes."""
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(float(a) - float(b)) < 1e-12
    return a == b


#: Verdicts from :func:`classify_param`.
WRITE, UNCHANGED, KEEP_USER = "write", "unchanged", "keep_user"


def classify_param(
    param: str,
    current: object,
    new_value: object,
    provenance: dict,
    preset: dict,
    *,
    absent: bool = False,
    force: bool = False,
) -> str:
    """Decide what a resolved value does to an existing config value.

    ``write``      — safe to set (absent, resolver-owned, or still the preset's value)
    ``unchanged``  — already equal
    ``keep_user``  — an explicit /set config edit; leave it alone

    Shared by :func:`apply_resolution` and ``/instrument show`` so the preview
    always matches what apply will actually do.
    """
    if absent:
        return WRITE
    if _same(current, new_value):
        return UNCHANGED
    if force:
        return WRITE
    if param in provenance and _same(current, provenance[param]):
        return WRITE
    if param in preset and _same(current, preset[param]):
        return WRITE
    return KEEP_USER


def apply_resolution(
    config_id: str,
    resolution: Resolution,
    config_params: dict,
    provenance: dict,
    *,
    force: bool = False,
) -> ApplyOutcome:
    """Write a resolution into `config_params` (mutated in place).

    A parameter is written when it is absent, already equals the resolved
    value, was written by an earlier resolve (tracked in `provenance`), or
    still holds the JSON preset's value. Anything else is an explicit
    ``/set config`` edit and is kept — unless `force`.

    `provenance` is the per-config record (``state.instrument_provenance[cfg]``)
    and is updated to match what is now in place.
    """
    from eqsanscli.services.config_manager import _load_matching_preset

    outcome = ApplyOutcome(config_id=config_id, resolution=resolution)
    if not resolution.params:
        return outcome

    preset = _load_matching_preset(config_id)

    for param, resolved in resolution.params.items():
        new_value = resolved.value
        absent = param not in config_params
        current = config_params.get(param)
        verdict = classify_param(
            param, current, new_value, provenance, preset,
            absent=absent, force=force,
        )
        if verdict == WRITE:
            config_params[param] = new_value
            outcome.written[param] = new_value
            provenance[param] = new_value
        elif verdict == UNCHANGED:
            outcome.unchanged.append(param)
            provenance[param] = new_value
        else:
            outcome.kept_user[param] = current

    return outcome


# --------------------------------------------------------------------------
# Session-level entry point (used by /instrument, /matchruns and autopilot)
# --------------------------------------------------------------------------

def runs_in(row) -> list[int]:
    """Run numbers on a working-table row (``scattering_run`` may be a list)."""
    out: list[int] = []
    for part in str(getattr(row, "scattering_run", "") or "").split(","):
        part = part.strip()
        if part.isdigit():
            out.append(int(part))
    return out


@dataclass
class ConfigTarget:
    """What a working-table config needs resolved."""

    config_id: str
    run: int  # the run the resolution is keyed on (lowest in the config)
    distance: float
    max_run: int
    n_rows: int


def config_targets(state) -> list[ConfigTarget]:
    """One target per config in the active working table.

    Keyed on the *lowest* run in each config: calibration valid when the
    measurement series started. `max_run` lets callers warn when a config
    straddles a cycle boundary.
    """
    table = state.current_table
    grouped: dict[str, list] = {}
    for row in table.rows:
        grouped.setdefault(row.configuration, []).append(row)

    targets: list[ConfigTarget] = []
    for config_id, rows in grouped.items():
        runs = [r for row in rows for r in runs_in(row)]
        if not runs:
            continue
        distance = next(
            (row.detector_distance for row in rows if row.detector_distance), 0.0
        )
        targets.append(ConfigTarget(
            config_id=config_id, run=min(runs), distance=distance,
            max_run=max(runs), n_rows=len(rows),
        ))
    targets.sort(key=lambda t: t.config_id)
    return targets


def sync_state_configs(state, *, force: bool = False) -> tuple[list[ApplyOutcome], list[str]]:
    """Resolve and apply instrument files for every config in the working table.

    Returns (outcomes, warnings). Honours ``state.instrument_cycle_pin``.
    Never raises on a missing share — the reason lands in the resolution's
    `missing` list instead.
    """
    cycles = scan_cycles()
    outcomes: list[ApplyOutcome] = []
    warnings: list[str] = []
    pin = getattr(state, "instrument_cycle_pin", "") or None

    for target in config_targets(state):
        resolution = resolve_for_run(
            target.run, target.distance, cycles=cycles, pin_cycle=pin,
        )
        params = state.configurations.setdefault(target.config_id, {})
        provenance = state.instrument_provenance.setdefault(target.config_id, {})
        outcomes.append(apply_resolution(
            target.config_id, resolution, params, provenance, force=force,
        ))

        # Data spanning a cycle boundary: the whole config would be reduced with
        # the earlier cycle's calibration. Flag it rather than split silently.
        if not pin and target.max_run != target.run:
            later = resolve_for_run(target.max_run, target.distance, cycles=cycles)
            if later.cycle_id and later.cycle_id != resolution.cycle_id:
                warnings.append(
                    f"{target.config_id}: runs {target.run}-{target.max_run} straddle a "
                    f"calibration boundary ({resolution.cycle_id} → {later.cycle_id}). "
                    f"All rows use {resolution.cycle_id}; split the later runs into "
                    f"their own table if you need {later.cycle_id}."
                )

    return outcomes, warnings


def verify_paths(values: dict[str, object]) -> list[str]:
    """Report missing or empty files among path-valued params."""
    problems: list[str] = []
    for param in (PARAM_SENSITIVITY, PARAM_DARK, PARAM_FLUX):
        val = values.get(param)
        if not val or not isinstance(val, str):
            continue
        if not os.path.exists(val):
            problems.append(f"{PARAM_LABELS[param]}: missing file {val}")
        elif os.path.getsize(val) == 0:
            problems.append(f"{PARAM_LABELS[param]}: empty file {val}")
    return problems
