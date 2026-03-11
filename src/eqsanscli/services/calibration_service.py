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

REFERENCE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "absscale_reference"

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


def find_scale_factor(
    measured_file: str,
    reference: str = DEFAULT_REFERENCE,
    qmin: float = 0.01,
    qmax: float = 0.1,
) -> CalibrationResult:
    ref_path = _resolve_reference(reference)
    ref = load_iq_native(ref_path)
    meas = load_iq_native(measured_file)

    mask_ref = (ref.mod_q >= qmin) & (ref.mod_q <= qmax)
    q_ref_overlap = ref.mod_q[mask_ref]
    i_ref_overlap = ref.intensity[mask_ref]

    if len(q_ref_overlap) < 2:
        raise ValueError(f"Fewer than 2 reference points in Q range [{qmin}, {qmax}]")

    interp_meas = interp1d(meas.mod_q, meas.intensity, bounds_error=False, fill_value=np.nan)
    i_meas_interp = interp_meas(q_ref_overlap)

    valid = np.isfinite(i_meas_interp) & (i_meas_interp > 0)
    if np.sum(valid) < 2:
        raise ValueError(f"Fewer than 2 valid measured points in Q range [{qmin}, {qmax}]")

    scale = float(np.mean(i_ref_overlap[valid] / i_meas_interp[valid]))

    return CalibrationResult(
        scale_factor=scale,
        qmin=qmin,
        qmax=qmax,
        reference_file=ref_path,
        measured_file=measured_file,
        n_points=int(np.sum(valid)),
    )


def _resolve_reference(reference: str) -> str:
    if os.path.exists(reference):
        return reference

    upper = reference.upper()
    if upper in REFERENCE_FILES:
        path = REFERENCE_DIR / REFERENCE_FILES[upper]
        if path.exists():
            return str(path)

    for name, fname in REFERENCE_FILES.items():
        path = REFERENCE_DIR / fname
        if path.exists():
            return str(path)

    # Fallback to eqsanstools location
    fallback = f"/SNS/EQSANS/shared/script/eqsanstools/{REFERENCE_FILES.get(upper, REFERENCE_FILES[DEFAULT_REFERENCE])}"
    if os.path.exists(fallback):
        return fallback

    raise FileNotFoundError(f"Reference file not found for '{reference}'")


def list_references() -> list[dict[str, str]]:
    refs = []
    for name, fname in REFERENCE_FILES.items():
        path = REFERENCE_DIR / fname
        exists = path.exists()
        refs.append({"name": name, "file": fname, "exists": "yes" if exists else "no"})
    return refs
