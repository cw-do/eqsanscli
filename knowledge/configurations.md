---
topic: configurations
summary: Per-configuration reduction parameters and why those values are used.
load: on-demand
updated: 2026-08-17
---

# Configuration parameters and their rationale

A configuration is `(detector distance, wavelength, chopper frequency)`, written
compactly: `4m10a`, `4m2.5a`, `2.5m2.5a`, `8m12a`, `4m2.5a30hz` (60 Hz is the
default and omitted).

Values below are the *typical* starting points and the reasoning behind them —
not a substitute for the JSON presets in `preset_configs/`, which are what the
tool actually applies. When a preset and this document disagree, the preset is
what ran; fix whichever is wrong.

Parameter names here are the drtsans-wrapper names (`eq._numqbins`); the JSON
keys match case-insensitively (`numQBins` → stored as `numqbins`).

## What each parameter is

One line per parameter the tool manages. Exact semantics belong to drtsans; this
says what the parameter is for and who sets it. `eq._name` is how it appears in a
script written by `/export script`.

| Parameter | What it is |
|---|---|
| `standardabsolutescale` | Factor putting the reduced intensity on an absolute scale, from a standard measured in that same configuration (SCL-02) |
| `sampleaperturesize` | Sample aperture diameter in mm; feeds the resolution calculation |
| `maskfilename` | Detector mask applied to every run in the configuration |
| `sensitivityfilename` | Flood map correcting pixel-to-pixel response |
| `darkfilename` | Dark-current run subtracted as instrumental background |
| `beamfluxfilename` | Measured incident spectrum, used to normalise by wavelength |
| `numqbins` | Number of bins in the 1D I(Q) |
| `numqxqybins` | Bins per axis in the 2D I(Qx,Qy) |
| `qbintype` | Bin spacing for I(Q): `log` or `linear` |
| `qmin` / `qmax` | Q range kept in the 1D profile |
| `cuttofmin` / `cuttofmax` | Time-of-flight window kept, in µs; a narrow window approximates a monochromatic beam |
| `wavelengthstep` | Wavelength bin width in Å |
| `sampleoffset` | Sample position offset along the beam, mm — from AgBe calibration |
| `detectoroffset` | Detector position offset along the beam, mm — from AgBe calibration |
| `scalecomponents.detector1` | `[x, y, z]` scale of the detector geometry — from AgBe calibration |
| `fitinelasticincoh` | Whether to fit and remove incoherent inelastic scattering |
| `selectminincoh` | Used only when `fitinelasticincoh` is on |
| `incohfit_qmin` / `incohfit_qmax` | Q window that fit uses; must lie inside the configuration's range (CFG-02) |
| `useerrorweighting` | Weight by uncertainty when binning |
| `outputwavelengthdependentprofile` | Also write I(Q) per wavelength bin |
| `usemaskbacktubes` | Mask the back tube bank as well |
| `usetimeslice` / `timesliceinterval` | Split a run into time slices, and how long each slice is |

## Parameters that rarely change

| Parameter | Typical | Why |
|---|---|---|
| `sampleaperturesize` | 10 | default unless the experiment specifies otherwise |
| `wavelengthstep` | 0.1 | used for every configuration |
| `useerrorweighting` | True | usually on; see the 2.5 m note below |
| `qbintype` | `log` | log binning for I(Q) |
| `showjson` | False | |
| `selectminincoh` | True | only consulted when `fitinelasticincoh` is on |

`scalecomponents`, `sampleoffset`, `detectoroffset`: from the cycle's AgBe
calibration — see `instrument-files.md`, never typed by hand.

## Q range and binning

`numqbins` follows counting statistics: **40–60**, lower for low-Q
configurations, higher at short detector distances where statistics are better.

`qmin`/`qmax` bracket what the configuration can actually measure, usually cut
conservatively inside the accessible range (protocol CFG-01).

## Worked configurations

### 4 m, 10 Å — low-Q

```
numqbins   40
qmin       0.006      typical low-Q limit for 4m10a
qmax       0.1        typical high-Q cutoff
cuttofmin  1000       default TOF window for this configuration
cuttofmax  3000
fitinelasticincoh  False
incohfit_qmin 0.025   only used if the correction is turned on
incohfit_qmax 0.05
```

Incoherent inelastic correction is normally **off** at low Q. It matters at high
Q, or where incoherent background is significant.

### 2.5 m, 2.5 Å — high-Q

```
numqbins   60         better statistics at short distance
qmin       0.03       the configuration reaches 0.03 < q < 0.5
qmax       0.4        cut conservatively below the limit
cuttofmin  2000       narrow TOF window (see below)
cuttofmax  11000
fitinelasticincoh  False
incohfit_qmin 0.1
incohfit_qmax 0.30
useerrorweighting  False
outputwavelengthdependentprofile  True
```

The narrow TOF window is deliberate: looking at a narrow wavelength band
approximates a monochromatic beam, which minimises the incoherent inelastic
effect and yields a cleaner high-Q profile — at the cost of neutron counts. With
that cut in place, `fitinelasticincoh` does not need to be on.

The alternative is the full wavelength band with `cuttofmin 1000` /
`cuttofmax 2000` as defaults *and* the incoherent inelastic correction enabled.
Choose one approach or the other, not both.

When a custom TOF cut is used, mark the output filename (`_tofcut`) so the
profile is not mistaken for a full-band reduction (protocol CFG-04).

### Beyond 4 m (5 m, 8 m, 9 m)

Use the 4 m flood (protocol CAL-02). Q range shifts lower with distance; set
`qmin`/`qmax` from what the configuration reaches rather than copying 4 m values.

## Combination experiments

A 4 m 10 Å + 2.5 m 2.5 Å pair is the common low-Q/high-Q combination, stitched
into one profile afterwards (`stitching.md`). Each configuration keeps its own
`standardabsolutescale` from a standard measured in that configuration (protocol
SCL-02) — for the pair above, values near 0.2276 (4 m 10 Å, 2025-05-05) and
0.2473 × 1.078 × 0.7183 (2.5 m 2.5 Å) have been used; the multipliers there were
experiment-specific corrections, not a general rule.

## Parameters normally left alone

`elasticreference*` / `elasticreferencebkgd*` — elastic reference corrections are
not often used. `incohfit_factor`, `incohfit_intensityweighted` — only with the
incoherent inelastic correction, and rarely.
