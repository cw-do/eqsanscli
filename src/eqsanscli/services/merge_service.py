from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from eqsanscli.models.working_table import WorkingTable
from eqsanscli.services.plotting_service import load_iq_native


@dataclass
class StitchGroup:
    sample_name: str
    files: list[str] = field(default_factory=list)
    configs: list[str] = field(default_factory=list)
    overlaps: list[float] = field(default_factory=list)
    target_profile_index: int = 0
    output_file: str = ""
    status: str = "ready"

    def to_dict(self) -> dict:
        return {
            "sample_name": self.sample_name,
            "files": self.files,
            "configs": self.configs,
            "overlaps": self.overlaps,
            "target_profile_index": self.target_profile_index,
            "output_file": self.output_file,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict) -> StitchGroup:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


# ---------------------------------------------------------------------------
# Native stitch_profiles implementation
# (Port of drtsans.stitch.stitch_profiles without drtsans/mantid dependency)
# Source: https://github.com/neutrons/drtsans/blob/next/src/drtsans/stitch.py
# ---------------------------------------------------------------------------

def _scaling_factor(
    target_q: np.ndarray, target_i: np.ndarray,
    other_q: np.ndarray, other_i: np.ndarray,
    start_q: float, end_q: float,
) -> float:
    """Find the scale factor to bring `other` profile to `target` in the overlap region."""
    mask = (target_q >= start_q) & (target_q <= end_q) & np.isfinite(target_i)
    q_overlap = target_q[mask]
    if len(q_overlap) < 2:
        # Try widening by 20% on each side as fallback
        margin = (end_q - start_q) * 0.5
        wide_mask = (target_q >= start_q - margin) & (target_q <= end_q + margin) & np.isfinite(target_i)
        q_overlap_wide = target_q[wide_mask]
        if len(q_overlap_wide) >= 2:
            mask = wide_mask
            q_overlap = q_overlap_wide
        else:
            raise ValueError(
                f"Insufficient Q values in overlap region [{start_q:.5f}, {end_q:.5f}] "
                f"(found {len(q_overlap)}, need >=2). Try widening overlap or using more points."
            )

    good = np.isfinite(other_i)
    other_interp = np.interp(q_overlap, other_q[good], other_i[good])

    denom = np.sum(other_interp)
    if denom == 0.0:
        raise ValueError("Interpolated intensity sums to zero — cannot compute scale.")

    scale = float(np.sum(target_i[mask]) / denom)
    if scale <= 0:
        raise ValueError(f"Negative scale factor ({scale:.3e}). Check overlap range or data.")
    return scale


def stitch_profiles(
    profiles: list[SimpleNamespace],
    overlaps: list[float],
    target_profile_index: int = 0,
) -> SimpleNamespace:
    """Stitch together I(Q) profiles with overlapping Q domains.

    Native implementation matching drtsans.stitch.stitch_profiles behavior.

    Parameters
    ----------
    profiles : list of SimpleNamespace
        Each has .mod_q, .intensity, .error (numpy arrays). Ordered by increasing Q.
    overlaps : list of float
        Flat list [start1, end1, start2, end2, ...] — 2*(N-1) values for N profiles.
    target_profile_index : int
        Which profile defines the absolute scale.

    Returns
    -------
    SimpleNamespace with .mod_q, .intensity, .error
    """
    n = len(profiles)
    if n < 2:
        return profiles[0] if profiles else SimpleNamespace(mod_q=np.array([]), intensity=np.array([]), error=np.array([]))

    # Convert flat overlap list to pairs
    if len(overlaps) != 2 * (n - 1):
        raise ValueError(f"Expected {2*(n-1)} overlap values for {n} profiles, got {len(overlaps)}")
    overlap_pairs = [(overlaps[i], overlaps[i + 1]) for i in range(0, len(overlaps), 2)]

    def _extract(p: SimpleNamespace, mask: np.ndarray) -> SimpleNamespace:
        return SimpleNamespace(
            mod_q=p.mod_q[mask],
            intensity=p.intensity[mask],
            error=p.error[mask] if p.error is not None else None,
        )

    def _concat(a: SimpleNamespace, b: SimpleNamespace) -> SimpleNamespace:
        err = None
        if a.error is not None and b.error is not None:
            err = np.concatenate([a.error, b.error])
        return SimpleNamespace(
            mod_q=np.concatenate([a.mod_q, b.mod_q]),
            intensity=np.concatenate([a.intensity, b.intensity]),
            error=err,
        )

    def _sort(p: SimpleNamespace) -> SimpleNamespace:
        order = np.argsort(p.mod_q)
        err = p.error[order] if p.error is not None else None
        return SimpleNamespace(mod_q=p.mod_q[order], intensity=p.intensity[order], error=err)

    def _scale(p: SimpleNamespace, s: float) -> SimpleNamespace:
        err = p.error * s if p.error is not None else None
        return SimpleNamespace(mod_q=p.mod_q, intensity=p.intensity * s, error=err)

    target = profiles[target_profile_index]

    # Stitch profiles with lower Q (going left from target)
    idx = target_profile_index - 1
    while idx >= 0:
        other = profiles[idx]
        start_q, end_q = overlap_pairs[idx]
        scale = _scaling_factor(target.mod_q, target.intensity, other.mod_q, other.intensity, start_q, end_q)
        other = _scale(other, scale)
        other = _extract(other, other.mod_q < end_q)
        target = _extract(target, target.mod_q > start_q)
        target = _sort(_concat(other, target))
        idx -= 1

    # Stitch profiles with higher Q (going right from target)
    idx = target_profile_index + 1
    while idx < n:
        other = profiles[idx]
        start_q, end_q = overlap_pairs[idx - 1]
        scale = _scaling_factor(target.mod_q, target.intensity, other.mod_q, other.intensity, start_q, end_q)
        other = _scale(other, scale)
        other = _extract(other, other.mod_q > start_q)
        target = _extract(target, target.mod_q < end_q)
        target = _sort(_concat(target, other))
        idx += 1

    return target


def save_iq(profile: SimpleNamespace, path: str) -> None:
    """Save I(Q) profile to tab-separated text file matching MantidAscii format."""
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("# I(Q)\n")
        f.write("#Q (1/A)\tI (1/cm)\tdI (1/cm)\n")
        for i in range(len(profile.mod_q)):
            q = profile.mod_q[i]
            intensity = profile.intensity[i]
            error = profile.error[i] if profile.error is not None else 0.0
            f.write(f"{q:.6E}\t{intensity:.6E}\t{error:.6E}\n")


# ---------------------------------------------------------------------------
# Stitch table building
# ---------------------------------------------------------------------------

def _is_frame_skipping(row) -> bool:
    """Check if a row is from a 30Hz frame-skipping configuration."""
    return getattr(row, "frequency", 60) == 30


def _find_frame_files(output_dir: str, sample_name: str, config: str) -> tuple[str, str]:
    """Find frame_0 and frame_1 output files for a frame-skipping run.

    Returns (frame_0_path, frame_1_path) or ("", "") if not found.
    """
    f0 = os.path.join(output_dir, f"{sample_name}_{config}_frame_0_Iq.dat")
    f1 = os.path.join(output_dir, f"{sample_name}_{config}_frame_1_Iq.dat")
    if os.path.exists(f0) and os.path.exists(f1):
        return f0, f1
    return "", ""


def build_stitch_table(table: WorkingTable, output_dir: str) -> list[StitchGroup]:
    """Build stitch groups by scanning output directory for *_Iq.dat files.

    Strategy 1: Match files to working table rows (uses row metadata for ordering).
    Strategy 2: If no table matches, scan output_dir and parse sample_config from filenames.

    For 30Hz frame-skipping configs, each run produces frame_0 (low-Q, long wavelength)
    and frame_1 (high-Q, short wavelength). These become two entries for stitching,
    even within a single config.

    IMPORTANT: 30Hz frame-skipping configs are grouped separately from 60Hz configs.
    A 30Hz config only stitches its own frame_0 + frame_1 pair; it is never mixed
    with 60Hz configs even for the same sample and detector distance.
    """
    # Use (sample_name, freq_group) as key to separate 30Hz from 60Hz
    # Tuple: (file_path, config_id, distance, wavelength)
    sample_files: dict[str, list[tuple[str, str, float, float]]] = {}

    for row in table.rows:
        if _is_frame_skipping(row):
            f0, f1 = _find_frame_files(output_dir, row.sample_name, row.configuration)
            if f0 and f1:
                row.output_file = f0
                row.status = "done"
                # 30Hz entries get their own group key to prevent mixing with 60Hz
                group_key = f"{row.sample_name}__30hz__{row.configuration}"
                # frame_0 = low-Q (long wavelength) → larger virtual distance → listed first
                # frame_1 = high-Q (short wavelength) → smaller virtual distance → listed second
                sample_files.setdefault(group_key, []).append(
                    (f0, f"{row.configuration}_frame0", row.detector_distance + 0.01, row.wavelength + 0.01)
                )
                sample_files.setdefault(group_key, []).append(
                    (f1, f"{row.configuration}_frame1", row.detector_distance, row.wavelength)
                )
                continue

        fpath = row.output_file if row.output_file and os.path.exists(row.output_file) else ""
        if not fpath:
            fpath = os.path.join(output_dir, f"{row.sample_name}_{row.configuration}_Iq.dat")
        if os.path.exists(fpath):
            row.output_file = fpath
            row.status = "done"
            sample_files.setdefault(row.sample_name, []).append(
                (fpath, row.configuration, row.detector_distance, row.wavelength)
            )

    if not sample_files:
        sample_files = _scan_output_dir(output_dir)

    return _build_groups(sample_files, output_dir)


def _scan_output_dir(output_dir: str) -> dict[str, list[tuple[str, str, float, float]]]:
    import glob
    import re

    from eqsanscli.models.config_id import parse_config_id

    sample_files: dict[str, list[tuple[str, str, float, float]]] = {}
    iq_files = sorted(glob.glob(os.path.join(output_dir, "*_Iq.dat")))

    _DISTANCE_GUESS = {
        "8m": 8.0, "9m": 9.0, "4m": 4.0, "2.5m": 2.5, "2m": 2.0, "1.3m": 1.3, "1m": 1.0,
    }

    frame_pairs: dict[str, dict[str, str]] = {}

    for fpath in iq_files:
        stem = os.path.basename(fpath).replace("_Iq.dat", "")

        frame_match = re.match(r"^(.+?)_frame_([01])$", stem)
        if frame_match:
            base_stem = frame_match.group(1)
            frame_id = frame_match.group(2)
            frame_pairs.setdefault(base_stem, {})[frame_id] = fpath
            continue

        parts = stem.rsplit("_", 1)
        if len(parts) != 2:
            continue
        sample_name, config_str = parts[0], parts[1]

        dist, wl, _freq = parse_config_id(config_str)
        if dist == 0.0:
            # Fallback: guess distance from prefix
            distance = 4.0
            for prefix, d in _DISTANCE_GUESS.items():
                if config_str.lower().startswith(prefix):
                    distance = d
                    break
            dist = distance
            wl = 0.0

        sample_files.setdefault(sample_name, []).append(
            (fpath, config_str, dist, wl)
        )

    for base_stem, frames in frame_pairs.items():
        if "0" not in frames or "1" not in frames:
            continue
        parts = base_stem.rsplit("_", 1)
        if len(parts) != 2:
            continue
        sample_name, config_str = parts[0], parts[1]

        dist, wl, _freq = parse_config_id(config_str)
        if dist == 0.0:
            distance = 4.0
            for prefix, d in _DISTANCE_GUESS.items():
                if config_str.lower().startswith(prefix):
                    distance = d
                    break
            dist = distance
            wl = 0.0

        group_key = f"{sample_name}__30hz__{config_str}"
        sample_files.setdefault(group_key, []).append(
            (frames["0"], f"{config_str}_frame0", dist + 0.01, wl + 0.01)
        )
        sample_files.setdefault(group_key, []).append(
            (frames["1"], f"{config_str}_frame1", dist, wl)
        )

    return sample_files


def _config_sort_key(entry: tuple[str, str, float, float]) -> tuple[float, float, float]:
    """Return a sort key for ordering configs from lower-Q to higher-Q.

    Priority (each returns early if matched):
    1. Standard config IDs (e.g. 4m10a): sort by (-distance, -wavelength)
    2. frame_0/frame_1: frame_0 = lower-Q (sorts first)
    3. lowq/lq/low variants: sort first; highq/hq/high variants: sort last
    4. confN / configN: sort by numeric index (conf0 = lower-Q first)
    5. Unknown: preserve original order via a neutral rank

    Args:
        entry: (file_path, config_id, distance, wavelength)
    Returns:
        Tuple of floats suitable for ascending sort (lower = lower-Q = comes first)
    """
    import re

    _fpath, config_id, distance, wavelength = entry
    cfg_lower = config_id.strip().lower()

    # 1. Standard config ID with known distance/wavelength
    if distance > 0 and wavelength > 0:
        return (-distance, -wavelength, 0.0)

    # 2. 30Hz frame identifiers
    frame_m = re.search(r"frame[_\s]?(\d+)$", cfg_lower)
    if frame_m:
        frame_num = int(frame_m.group(1))
        # frame_0 = lower-Q → rank 0, frame_1 = higher-Q → rank 1
        return (0.0, float(frame_num), 0.0)

    # 3. Explicit low/high Q naming
    _LOW_PATTERNS = ("lowq", "lq", "low_q", "low-q", "loq")
    _HIGH_PATTERNS = ("highq", "hq", "high_q", "high-q", "hiq")
    for pat in _LOW_PATTERNS:
        if pat in cfg_lower:
            return (0.0, 0.0, 0.0)  # sort first
    for pat in _HIGH_PATTERNS:
        if pat in cfg_lower:
            return (0.0, 0.0, 999.0)  # sort last

    # 4. confN / configN — numeric suffix determines order
    conf_m = re.match(r"^(?:conf|config)\s*(\d+)$", cfg_lower)
    if conf_m:
        conf_num = int(conf_m.group(1))
        # conf0 = lower-Q → rank 0, conf1 → rank 1, etc.
        return (0.0, 0.0, float(conf_num))

    # 5. Unknown — use a neutral rank; group by same config_id preserving order
    return (0.0, 0.0, 500.0)


def _build_groups(
    sample_files: dict[str, list[tuple[str, str, float, float]]], output_dir: str
) -> list[StitchGroup]:
    groups = []
    for group_key, entries in sorted(sample_files.items()):
        # Extract real sample name from composite keys like "mysample__30hz__4m2.5a30hz"
        if "__30hz__" in group_key:
            sample_name = group_key.split("__30hz__")[0]
        else:
            sample_name = group_key

        if len(entries) < 2:
            groups.append(StitchGroup(
                sample_name=sample_name,
                files=[f for f, _, _, _ in entries],
                configs=[c for _, c, _, _ in entries],
                status="1 config",
            ))
            continue

        # Sort: lower-Q first using heuristic sort key
        entries.sort(key=_config_sort_key)
        files = [f for f, _, _, _ in entries]
        configs = [c for _, c, _, _ in entries]
        overlaps = _auto_suggest_overlaps(files)

        groups.append(StitchGroup(
            sample_name=sample_name,
            files=files,
            configs=configs,
            overlaps=overlaps,
            target_profile_index=0,
            output_file=os.path.join(output_dir, f"merged_{sample_name}_Iq.txt"),
        ))

    return groups


def _auto_suggest_overlaps(files: list[str]) -> list[float]:
    """Suggest overlap Q ranges by finding Q intersection of adjacent files."""
    overlaps: list[float] = []
    for i in range(len(files) - 1):
        try:
            iq_low = load_iq_native(files[i])
            iq_high = load_iq_native(files[i + 1])
            overlap_start = max(float(iq_high.mod_q[0]), float(iq_low.mod_q[0]))
            overlap_end = min(float(iq_low.mod_q[-1]), float(iq_high.mod_q[-1]))
            if overlap_start < overlap_end:
                margin = (overlap_end - overlap_start) * 0.1
                overlaps.extend([round(overlap_start + margin, 6), round(overlap_end - margin, 6)])
            else:
                overlaps.extend([round(float(iq_high.mod_q[0]), 6), round(float(iq_low.mod_q[-1]), 6)])
        except Exception:
            overlaps.extend([0.0, 0.0])
    return overlaps


def run_stitch(group: StitchGroup) -> str:
    """Execute stitching for a single group. Returns output file path."""
    profiles = [load_iq_native(f) for f in group.files]
    stitched = stitch_profiles(profiles, group.overlaps, group.target_profile_index)
    save_iq(stitched, group.output_file)
    group.status = "done"
    return group.output_file


# ---------------------------------------------------------------------------
# Persistence + script export
# ---------------------------------------------------------------------------

def save_stitch_table(groups: list[StitchGroup], path: str) -> None:
    with open(path, "w") as f:
        json.dump([g.to_dict() for g in groups], f, indent=2)


def load_stitch_table(path: str) -> list[StitchGroup]:
    with open(path) as f:
        return [StitchGroup.from_dict(d) for d in json.load(f)]


def generate_stitch_script(groups: list[StitchGroup], output_path: str) -> str:
    from eqsanscli.services.script_exporter import _extract_path_vars

    all_paths: list[str] = []
    for group in groups:
        if group.status == "1 config" or len(group.files) < 2:
            continue
        all_paths.extend(group.files)
        if group.output_file:
            all_paths.append(group.output_file)

    var_defs, path_replacements = _extract_path_vars(all_paths)

    lines = [
        "#!/usr/bin/env python3",
        "# Stitch script generated by eqsanscli",
        "",
        "from drtsans.dataobjects import load_iqmod, save_iqmod",
        "from drtsans.stitch import stitch_profiles",
        "",
    ]

    if var_defs:
        for var_name, dirpath in var_defs.items():
            lines.append(f"{var_name} = '{dirpath}'")
        lines.append("")

    for group in groups:
        if group.status == "1 config" or len(group.files) < 2:
            continue
        lines.append(f"# {group.sample_name} ({', '.join(group.configs)})")
        lines.append(f"overlap = {group.overlaps}")
        for i, f in enumerate(group.files):
            f_expr = path_replacements.get(f, f"'{f}'")
            lines.append(f"iq{i} = load_iqmod({f_expr}, sep='\\t', header_type='MantidAscii')")
        iq_list = ", ".join(f"iq{i}" for i in range(len(group.files)))
        n = 2 * (len(group.files) - 1)
        lines.append(f"stitched = stitch_profiles([{iq_list}], overlap[0:{n}], target_profile_index={group.target_profile_index})")
        out_expr = path_replacements.get(group.output_file, f"'{group.output_file}'")
        lines.append(f"save_iqmod(stitched, {out_expr}, sep=' ', float_format='%.6E')")
        lines.append(f"print('Saved:', {out_expr})")
        lines.append("")

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        f.write("\n".join(lines))
    return output_path
