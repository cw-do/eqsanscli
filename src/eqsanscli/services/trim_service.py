"""Remove the first N / last N points of an I(Q) profile, or points outside a Q range.

Used by `/trim` (finished files: a reduced I(Q) or a merged/stitched file) and by
the stitch table's per-config trim (`/stitch set … trim <config>`, applied to each
curve before stitching). "Points" are *real* points — finite, non-zero
intensity — so the NaN/empty rows drtsans leaves at the edges of a profile do
not count toward N (and go with the trimmed edge).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from types import SimpleNamespace

import numpy as np


@dataclass
class TrimSpec:
    first: int = 0
    last: int = 0
    qmin: float | None = None
    qmax: float | None = None

    def is_empty(self) -> bool:
        return not (self.first or self.last or self.qmin is not None or self.qmax is not None)

    def to_dict(self) -> dict:
        return {k: v for k, v in (("first", self.first), ("last", self.last),
                                  ("qmin", self.qmin), ("qmax", self.qmax)) if v}

    @classmethod
    def from_dict(cls, d: dict | None) -> "TrimSpec":
        d = d or {}
        return cls(int(d.get("first") or 0), int(d.get("last") or 0),
                   d.get("qmin"), d.get("qmax"))

    def describe(self) -> str:
        parts = []
        if self.first:
            parts.append(f"first {self.first}")
        if self.last:
            parts.append(f"last {self.last}")
        if self.qmin is not None:
            parts.append(f"Q < {self.qmin:g}")
        if self.qmax is not None:
            parts.append(f"Q > {self.qmax:g}")
        return ", ".join(parts) or "nothing"


@dataclass
class TrimResult:
    keep: np.ndarray                      # boolean mask over the input rows
    n_before: int                         # real points before
    n_after: int                          # real points after
    removed_low: list = field(default_factory=list)    # [qmin, qmax] of removed low-Q real points
    removed_high: list = field(default_factory=list)   # same for the high-Q end

    def summary(self) -> str:
        bits = [f"{self.n_before} → {self.n_after} points"]
        if self.removed_low:
            bits.append(f"low-Q removed {self.removed_low[0]:.4g}–{self.removed_low[1]:.4g}")
        if self.removed_high:
            bits.append(f"high-Q removed {self.removed_high[0]:.4g}–{self.removed_high[1]:.4g}")
        return ", ".join(bits)


def trim_mask(q: np.ndarray, intensity: np.ndarray, spec: TrimSpec) -> TrimResult:
    """Which rows to keep. Raises ValueError if nothing real would remain."""
    q = np.asarray(q, dtype=float)
    i = np.asarray(intensity, dtype=float)
    order = np.argsort(q, kind="stable")
    real = np.isfinite(i) & (i != 0) & np.isfinite(q)
    keep = np.ones(len(q), dtype=bool)
    if spec.qmin is not None:
        keep &= q >= spec.qmin
    if spec.qmax is not None:
        keep &= q <= spec.qmax
    real_sorted = [idx for idx in order if real[idx] and keep[idx]]
    if spec.first:
        cut = real_sorted[:spec.first]
        if cut:
            keep &= q > q[cut[-1]]          # and every row below it (leading NaNs too)
    if spec.last:
        cut = real_sorted[-spec.last:] if spec.last <= len(real_sorted) else real_sorted
        if cut:
            keep &= q < q[cut[0]]
    n_before = int(real.sum())
    n_after = int((real & keep).sum())
    if n_after == 0:
        raise ValueError(f"trimming {spec.describe()} would leave no points (of {n_before})")
    gone = real & ~keep
    kept_q = q[real & keep]
    low = q[gone & (q < kept_q.min())]
    high = q[gone & (q > kept_q.max())]
    return TrimResult(keep, n_before, n_after,
                      [float(low.min()), float(low.max())] if low.size else [],
                      [float(high.min()), float(high.max())] if high.size else [])


def trim_profile(profile: SimpleNamespace, spec: TrimSpec) -> tuple[SimpleNamespace, TrimResult]:
    """A trimmed copy of an I(Q) namespace (mod_q, intensity, error, …)."""
    res = trim_mask(profile.mod_q, profile.intensity, spec)
    k = res.keep
    out = SimpleNamespace(**{
        name: (val[k] if isinstance(val, np.ndarray) and val.shape[:1] == k.shape else val)
        for name, val in vars(profile).items()
    })
    return out, res


def trim_file(path: str, spec: TrimSpec, output: str | None = None,
              inplace: bool = False) -> dict:
    """Trim an I(Q) text file (any column count, `#` header kept) into `output`
    (default `<name>_trim<ext>`, which `*_Iq.dat` globs do not pick up). With
    `inplace`, the file is rewritten and the original kept once as
    `<name>.untrimmed`. A `# trimmed:` header line records what was cut."""
    with open(path) as f:
        lines = f.readlines()
    header = [ln for ln in lines if ln.lstrip().startswith("#")]
    data = np.loadtxt(path, comments="#", ndmin=2)
    if data.shape[1] < 2:
        raise ValueError(f"{os.path.basename(path)}: need at least Q and I columns")
    res = trim_mask(data[:, 0], data[:, 1], spec)
    kept = data[res.keep]

    if inplace:
        backup = path + ".untrimmed"
        if not os.path.exists(backup):
            with open(backup, "w") as f:
                f.writelines(lines)
        out = path
    else:
        root, ext = os.path.splitext(path)
        out = output or f"{root}_trim{ext or '.dat'}"
        if os.path.abspath(out) == os.path.abspath(path):
            raise ValueError("output is the input file — use --inplace to overwrite")

    note = f"# trimmed: {spec.describe()} ({res.summary()}) from {os.path.basename(path)}\n"
    # Keep the leading comment block, then the note just before the column-name line.
    with open(out, "w") as f:
        if header:
            f.writelines(header[:-1])
            f.write(note)
            f.write(header[-1])
        else:
            f.write(note)
        for row in kept:
            f.write("\t".join(f"{v:.6E}" for v in row) + "\n")
    return {"input": os.path.abspath(path), "output": os.path.abspath(out),
            "spec": spec.to_dict(), "n_before": res.n_before, "n_after": res.n_after,
            "removed_low": res.removed_low, "removed_high": res.removed_high,
            "backup": (path + ".untrimmed") if inplace else None}
