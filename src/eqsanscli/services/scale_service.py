"""Where each configuration's absolute scale came from, and what unit it implies.

`configurations[cfg]["standardabsolutescale"]` is a bare float; this module keeps
its origin beside it in `state.scale_provenance[cfg]`, so `/show config`, plots,
merged-file headers and NOTE.md can say whether intensities are absolute (1/cm)
or relative (a.u.) instead of guessing. Policy (owner, 2026-10-15; protocol
SCL-01..SCL-04):

  * no standard calibrated → scale 1.0, intensities **relative (a.u.)**
  * a scale set explicitly by the user is assumed correct → absolute (1/cm),
    even when borrowed from another experiment — that is the user's decision
  * presets never carry a scale (they held other experiments' factors)
  * plausible range 0.01–50; outside it warns, never refuses

Kinds:
  default    1.0, nothing calibrated                       → a.u.
  calibrate  /calibrate --applynow or autopilot Step 8      → 1/cm
  user       /set config … standardabsolutescale, or a user JSON via /apply preset → 1/cm
  (absent)   set before v0.48.0, origin unknown — 1.0 is read as default,
             anything else is flagged
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from eqsanscli.models.session_state import SessionState

SCALE_PARAM = "standardabsolutescale"
PLAUSIBLE = (0.01, 50.0)            # SCL-03
STITCH_PLAUSIBLE = (0.01, 1000.0)   # STC-05


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _key(state: "SessionState", cfg: str) -> str:
    """The provenance key for `cfg`: its stored configurations key if one matches."""
    from eqsanscli.models.config_id import normalize_config_id
    if cfg in state.configurations:
        return cfg
    norm = normalize_config_id(cfg)
    for k in state.configurations:
        if normalize_config_id(k) == norm:
            return k
    return cfg


def current_scale(state: "SessionState", cfg: str) -> float:
    try:
        return float(state.configurations.get(_key(state, cfg), {}).get(SCALE_PARAM, 1.0))
    except (TypeError, ValueError):
        return 1.0


def record(state: "SessionState", cfg: str, kind: str, **details) -> dict:
    """Store the origin of `cfg`'s current scale. Returns the stored entry."""
    entry = {"kind": kind, "value": current_scale(state, cfg), "utc": _utc()}
    entry.update({k: v for k, v in details.items() if v is not None})
    state.scale_provenance[_key(state, cfg)] = entry
    return entry


def provenance(state: "SessionState", cfg: str) -> Optional[dict]:
    return state.scale_provenance.get(_key(state, cfg))


def is_relative(state: "SessionState", cfg: str) -> Optional[bool]:
    """True = a.u., False = absolute (1/cm), None = unknown origin."""
    p = provenance(state, cfg)
    if p:
        return p.get("kind") == "default"
    return True if abs(current_scale(state, cfg) - 1.0) < 1e-12 else None


def unit(state: "SessionState", cfg: str) -> str:
    rel = is_relative(state, cfg)
    return "a.u." if rel else ("1/cm" if rel is False else "1/cm?")


def describe(state: "SessionState", cfg: str) -> str:
    """One-line origin, e.g. '2.0459 (calibrate porsil_8m12a_Iq.dat, NG3, 0.01–0.03)'."""
    v = current_scale(state, cfg)
    p = provenance(state, cfg)
    kind = (p or {}).get("kind")
    if kind == "calibrate":
        how = (f"calibrate {p.get('measured_name', '?')}, {p.get('reference_name', '?')}, "
               f"{p.get('qmin')}–{p.get('qmax')}")
        stale = stale_reason(state, cfg)
        if stale:
            how += f"; STALE: {stale} — recalibrate"
        text = f"{v:.7g} ({how}) → 1/cm"
    elif kind == "user":
        note = f": {p['note']}" if p.get("note") else ""
        text = f"{v:.7g} (user, {p.get('utc', '')[:10]}{note}) → 1/cm"
    elif kind == "default" or (p is None and abs(v - 1.0) < 1e-12):
        text = f"{v:.7g} (no standard calibrated → relative, a.u.)"
    else:
        text = (f"{v:.7g} (origin unknown — set before v0.48.0, possibly another "
                f"experiment's preset; /calibrate, or /set config {cfg} "
                f"standardabsolutescale 1.0 for relative)")
    warn = plausibility(v)
    return f"{text}  ⚠ {warn}" if warn else text


def plausibility(value: float) -> str:
    lo, hi = PLAUSIBLE
    if value < lo or value > hi:
        return f"outside the plausible range {lo}–{hi} (SCL-03)"
    return ""


def unknown_origin(state: "SessionState", configs) -> list[str]:
    """Configs whose scale is not 1.0 and has no recorded origin (pre-0.48 sessions)."""
    return [c for c in configs if is_relative(state, c) is None]


# --- staleness (SCL-05) ---------------------------------------------------------
# Parameters that change the standard's I(Q), so a calibration made before they
# changed no longer fits (mask, Q binning, incoherent fit, TOF cuts, wavelength
# binning, flood, flux, normalization).
CALIBRATION_PHYSICS = (
    "maskfilename", "usedefaultmask", "defaultmask", "usemaskbacktubes",
    "numqbins", "qbintype", "1dqbintype", "logqbinsperdecade",
    "fitinelasticincoh", "selectminincoh", "incohfit_qmin", "incohfit_qmax",
    "incohfit_factor", "incohfit_intensityweighted",
    "cuttofmin", "cuttofmax", "wavelengthstep", "wavelengthsteptype",
    "sensitivityfilename", "beamfluxfilename", "normalization",
)


def physics_snapshot(json_path) -> dict:
    """The CALIBRATION_PHYSICS values the standard was actually reduced with,
    from its drtsans input json ({} if unreadable)."""
    import json
    from eqsanscli.services.preset_service import _flatten_config
    try:
        with open(json_path) as f:
            flat = _flatten_config(json.load(f))
    except (OSError, ValueError):
        return {}
    # Only what the json states: a parameter it does not mention cannot be said
    # to have changed (a partial or hand-made json would otherwise look stale).
    return {k: flat[k] for k in CALIBRATION_PHYSICS if k in flat}


def _same(a, b) -> bool:
    if a in (None, "") and b in (None, ""):
        return True
    try:
        return abs(float(a) - float(b)) <= 1e-9 * max(1.0, abs(float(a)))
    except (TypeError, ValueError):
        return str(a).strip().lower() == str(b).strip().lower()


def stale_reason(state: "SessionState", cfg: str) -> str:
    """'' when the calibration still fits the config, else which parameters moved."""
    p = provenance(state, cfg) or {}
    snap = p.get("physics")
    if p.get("kind") != "calibrate" or not snap:
        return ""
    from eqsanscli.services.config_manager import get_config
    cur = get_config(_key(state, cfg), state.configurations)
    moved = [k for k, v in snap.items() if not _same(cur.get(k), v)]
    if not moved:
        return ""
    more = f" (+{len(moved) - 3} more)" if len(moved) > 3 else ""
    return f"{', '.join(moved[:3])}{more} changed since the standard was reduced"
