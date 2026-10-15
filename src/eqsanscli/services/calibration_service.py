"""Absolute scale calibration — compare porsil data against reference standard.

Calculates scale factor by interpolating measured porsil I(Q) onto reference
Q points in an overlap region and computing the mean intensity ratio.

Based on find_scale_b1.py from eqsanstools.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from scipy.interpolate import interp1d

from eqsanscli.services.plotting_service import load_iq_native
from eqsanscli.paths import app_root

REFERENCE_DIR = app_root() / "absscale_reference"

REFERENCE_FILES = {
    "NG3": "NG3_B1_1413_4col.dat",
    "NG7": "NG7_ORNL_B1_All_4col.dat",
}

DEFAULT_REFERENCE = "NG3"


@dataclass
class CalibrationResult:
    scale_factor: float
    qmin: float
    qmax: float
    reference_file: str
    measured_file: str
    n_points: int
    # Spread of the per-point ratio I_ref / I_meas over the window; a flat ratio
    # (small std_rel) means the measured curve has the reference's shape.
    std_rel: float = 0.0
    # The factor in the window shifted down / up by half its width (None when
    # fewer than 2 points fall there) — a stable factor does not move.
    neighbour_factors: tuple = (None, None)
    q: np.ndarray | None = None
    ratio: np.ndarray | None = None


# Default window, used by /calibrate and autopilot alike (was 0.1 here and 0.03
# in the command). 2.5 m / 2.5 Å curves start above it: use --qmin 0.03 --qmax 0.1.
DEFAULT_QMIN = 0.01
DEFAULT_QMAX = 0.03
FLATNESS_LIMIT = 0.02   # ±2 %: spread or neighbour drift beyond this warns


def _ratio(ref, meas, qmin: float, qmax: float):
    """(q, I_ref/I_meas) over [qmin, qmax] on the reference's Q points."""
    mask_ref = (ref.mod_q >= qmin) & (ref.mod_q <= qmax)
    q = ref.mod_q[mask_ref]
    i_ref = ref.intensity[mask_ref]
    if len(q) < 2:
        return q, np.array([])
    interp_meas = interp1d(meas.mod_q, meas.intensity, bounds_error=False, fill_value=np.nan)
    i_meas = interp_meas(q)
    valid = np.isfinite(i_meas) & (i_meas > 0)
    return q[valid], i_ref[valid] / i_meas[valid]


def find_scale_factor(
    measured_file: str,
    reference: str = DEFAULT_REFERENCE,
    qmin: float = DEFAULT_QMIN,
    qmax: float = DEFAULT_QMAX,
) -> CalibrationResult:
    ref_path = _resolve_reference(reference)
    ref = load_iq_native(ref_path)
    meas = load_iq_native(measured_file)

    if np.sum((ref.mod_q >= qmin) & (ref.mod_q <= qmax)) < 2:
        raise ValueError(f"Fewer than 2 reference points in Q range [{qmin}, {qmax}]")
    q, ratio = _ratio(ref, meas, qmin, qmax)
    if len(ratio) < 2:
        raise ValueError(f"Fewer than 2 valid measured points in Q range [{qmin}, {qmax}]")

    scale = float(np.mean(ratio))
    std_rel = float(np.std(ratio) / scale) if scale else float("nan")

    half = (qmax - qmin) / 2.0
    neighbours = []
    for shift in (-half, +half):
        lo, hi = qmin + shift, qmax + shift
        if lo <= 0:
            neighbours.append(None)
            continue
        _, r = _ratio(ref, meas, lo, hi)
        neighbours.append(float(np.mean(r)) if len(r) >= 2 else None)

    return CalibrationResult(
        scale_factor=scale,
        qmin=qmin,
        qmax=qmax,
        reference_file=ref_path,
        measured_file=measured_file,
        n_points=int(len(ratio)),
        std_rel=std_rel,
        neighbour_factors=tuple(neighbours),
        q=q,
        ratio=ratio,
    )


def flatness_warnings(result: CalibrationResult) -> list[str]:
    """Why this factor might not be trustworthy (empty when the ratio is flat)."""
    out = []
    if result.std_rel > FLATNESS_LIMIT:
        out.append(f"ratio spread {result.std_rel:.1%} over the window (> {FLATNESS_LIMIT:.0%}) "
                   f"— the measured curve does not follow the reference's shape there")
    for label, f in zip(("lower", "upper"), result.neighbour_factors):
        if f is not None and abs(f / result.scale_factor - 1) > FLATNESS_LIMIT:
            out.append(f"the factor in the {label} neighbouring window is {f:.4g} "
                       f"({f / result.scale_factor - 1:+.1%})")
    return out


def _resolve_reference(reference: str) -> str:
    """A reference file path, or a known name (NG3, NG7). Never a substitute:
    an unknown name or a missing file is an error (before v0.48.0 a typo or a
    missing NG7 silently used NG3)."""
    if os.path.exists(reference):
        return reference

    upper = reference.upper()
    if upper not in REFERENCE_FILES:
        raise FileNotFoundError(
            f"Unknown reference '{reference}' — known: {', '.join(REFERENCE_FILES)}, "
            f"or give a file path")
    path = REFERENCE_DIR / REFERENCE_FILES[upper]
    if path.exists():
        return str(path)
    fallback = Path("/SNS/EQSANS/shared/script/eqsanstools") / REFERENCE_FILES[upper]
    if fallback.exists():
        return str(fallback)
    raise FileNotFoundError(f"Reference {upper} ({REFERENCE_FILES[upper]}) not found in {REFERENCE_DIR}")


def list_references() -> list[dict[str, str]]:
    refs = []
    for name, fname in REFERENCE_FILES.items():
        path = REFERENCE_DIR / fname
        exists = path.exists()
        refs.append({"name": name, "file": fname, "exists": "yes" if exists else "no"})
    return refs


# --- the measured standard's own records -------------------------------------

_IQ_SUFFIXES = ("_frame_0_Iq.dat", "_frame_1_Iq.dat", "_frame_0_Iq.txt", "_frame_1_Iq.txt",
                "_Iq.dat", "_Iq.txt", ".dat", ".txt")   # longest first


def output_stem(path: str) -> str:
    """`porsil_4m2.5a30hz` for `…/porsil_4m2.5a30hz_frame_0_Iq.dat` (longest suffix first;
    `_Iq.dat` used to win and leave `…30hz_frame_0`, so frame files never parsed)."""
    name = os.path.basename(path)
    for suffix in _IQ_SUFFIXES:
        if name.endswith(suffix):
            return name[: -len(suffix)]
    return os.path.splitext(name)[0]


def config_from_filename(path: str) -> str | None:
    import re
    m = re.search(r"(\d+\.?\d*m\d+\.?\d*a(?:\d+hz)?)$", output_stem(path).lower())
    return m.group(1) if m else None


def input_json(measured_file: str) -> Path:
    """The drtsans input json written beside the I(Q) file: `<stem>.json`."""
    return Path(measured_file).resolve().parent / f"{output_stem(measured_file)}.json"


def scale_reduced_with(measured_file: str) -> float | None:
    """The StandardAbsoluteScale the standard was reduced with (None if unknown)."""
    import json
    p = input_json(measured_file)
    try:
        with open(p) as f:
            v = json.load(f).get("configuration", {}).get("StandardAbsoluteScale")
        return float(v) if v is not None else None
    except (OSError, ValueError, TypeError, AttributeError):
        return None


def sha256(path: str) -> str:
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def calibration_payload(result: CalibrationResult, *, config: str | None,
                        porsil_scale: float | None, applied: bool,
                        previous_scale: float | None) -> dict:
    """The machine-readable result of one calibration (headless `data`, and the
    record written to `calibration_<cfg>.json`). Change only additively."""
    from datetime import datetime, timezone
    new = porsil_scale * result.scale_factor if porsil_scale is not None else None
    return {
        "type": "calibration",
        "factor": result.scale_factor,
        "std_rel": result.std_rel,
        "n_points": result.n_points,
        "qmin": result.qmin,
        "qmax": result.qmax,
        "neighbour_factors": list(result.neighbour_factors),
        "reference": os.path.abspath(result.reference_file),
        "reference_sha256": sha256(result.reference_file),
        "measured": os.path.abspath(result.measured_file),
        "measured_sha256": sha256(result.measured_file),
        "porsil_scale": porsil_scale,
        "new_scale": new,
        "config": config,
        "applied": applied,
        "previous_scale": previous_scale,
        "warnings": flatness_warnings(result),
        "utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def write_record(payload: dict, result: CalibrationResult, out_dir: str) -> dict[str, str]:
    """calibration_<cfg>.json (latest), calibration_history.jsonl (all), and a PNG
    of reference vs I_meas × factor with the window shaded. Returns the paths."""
    import json
    cfg = payload.get("config") or output_stem(result.measured_file)
    os.makedirs(out_dir, exist_ok=True)
    rec = os.path.join(out_dir, f"calibration_{cfg}.json")
    with open(rec, "w") as f:
        json.dump(payload, f, indent=2)
    with open(os.path.join(out_dir, "calibration_history.jsonl"), "a") as f:
        f.write(json.dumps(payload) + "\n")
    paths = {"record": rec, "history": os.path.join(out_dir, "calibration_history.jsonl")}
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        ref = load_iq_native(result.reference_file)
        meas = load_iq_native(result.measured_file)
        fig, ax = plt.subplots(figsize=(6, 4.2), dpi=120)
        ax.loglog(ref.mod_q, ref.intensity, "k-", lw=1.2, label=f"reference {os.path.basename(result.reference_file)}")
        ax.loglog(meas.mod_q, meas.intensity * result.scale_factor, "o", ms=3,
                  label=f"{os.path.basename(result.measured_file)} × {result.scale_factor:.4g}")
        ax.axvspan(result.qmin, result.qmax, color="tab:orange", alpha=0.15,
                   label=f"window {result.qmin}–{result.qmax} Å⁻¹ (spread {result.std_rel:.1%})")
        ax.set_xlabel("Q (1/Å)")
        ax.set_ylabel("I (1/cm)")
        ax.legend(fontsize=7)
        fig.tight_layout()
        png = os.path.join(out_dir, f"calibration_{cfg}.png")
        fig.savefig(png)
        plt.close(fig)
        paths["png"] = png
    except Exception:
        pass
    return paths
