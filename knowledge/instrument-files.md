---
topic: instrument-files
summary: How mask, flood, dark current, flux and the AgBe offsets are chosen for a run.
load: on-demand
updated: 2026-08-17
---

# Instrument calibration files

Six parameters are properties of the **accelerator cycle**, not of an instrument
configuration: `maskfilename`, `sensitivityfilename`, `darkfilename`,
`beamfluxfilename`, `detectoroffset`, `scalecomponents.detector1` (and
`sampleoffset`). They are resolved from the run number at runtime by
`services/instrument_files.py`.

**Do not write current filenames into this document or into a preset.** They go
stale within one cycle — that is exactly how the previous knowledge file ended up
naming 2025B files three cycles late. Filenames below are worked examples,
labelled with their cycle.

## Where the files live

`/SNS/EQSANS/shared/NeXusFiles/EQSANS/<year><A|B>_mp/` per cycle:

| Artifact | Pattern | Example (2026B) |
|---|---|---|
| dark current | `EQSANS_<run>.nxs.h5` | `EQSANS_186198.nxs.h5` |
| flood / sensitivity | `Sensitivity_patched_<variant>_<tag>_<run>.nxs` | `Sensitivity_patched_thinPMMA_4m_186200.nxs` |
| beam flux | `bl6_flux_<cycle>_<month>_rebinned.txt` | `bl6_flux_2026B_aug_rebinned.txt` |
| AgBe calibration | `agbe_calibration/**/checkpoint.json` + `calibration_report.txt` | `detoffset = 66.763` |
| cycle mask | `masks/*mask.nxs` | `EQSANS_186104_mask.nxs` |

The machine-physics web page (`https://cw-do.github.io/eqsans_mp/`) is *generated
from* these folders by `<mp_root>/doc/generate.py`. The folder is the source of
truth; the page is a derived view with a publish lag.

## Which cycle applies

The newest cycle whose calibration campaign started at or before the data run —
its *anchor run*, the lowest dark/flood run in the folder. The whole set then
comes from that one cycle rather than being mixed (protocol CAL-03).

Anchor runs increase strictly across every cycle from 2011B (5702) to 2026B
(186198), so ordering by run number and ordering by cycle agree.

A data run can fall between a cycle's dark run and its flood runs — 186199 sits
between dark 186198 and floods 186200–186202. Taking the cycle as a unit is
deliberate: a flood characterises the detector, not the run, so using it for a
slightly earlier run is harmless, whereas pairing this cycle's dark with last
cycle's floods is not.

## Flood ↔ detector distance

Floods exist at three distances. Map the measured distance by clamping into that
range and taking the nearest, ties to the larger (protocol CAL-02):

| Measured | Flood |
|---|---|
| 1.3 m | `1o3m` |
| 2.0 m, 2.5 m | `2o5m` |
| 4 m | `4m` |
| beyond 4 m (5 m, 8 m, 9 m) | `4m` |

Within a cycle, prefer the `thinPMMA` variant. 2025B also carries `5mmPMMA` maps
whose run numbers are *higher*, so a purely run-driven pick would silently switch
variants. An undecorated distance tag beats a decorated one (`4m` over `4mSM`),
then the highest run — some cycles hold several flood generations (2022A has
four).

## Masks

A mask belongs to an **experiment**, not a configuration or a cycle. Search order,
first match wins:

1. the folder eqsanscli was started in — any `mask*.nxs`
2. `/SNS/EQSANS/IPTS-<current>/shared/`
3. `<cycle>_mp/masks/*mask.nxs` — the cycle default

Never another IPTS's shared folder (protocol CAL-04). Matching within a folder
uses the filename: the distance must agree, a matching wavelength is preferred,
`_FS` breaks ties for 30 Hz. `2p5` and `2o5` both mean 2.5 Å.

Worked example, IPTS-38773: `maskWS4m10A.nxs` serves `4m10a` and
`maskWS4m2p5A_FS.nxs` serves `4m2.5a`. A mask naming a different distance or
wavelength is not borrowed — a token-less mask (the cycle default) serves any
configuration.

The same mask is often reusable across detector distances, so a single
`mask_4m.nxs` in the working folder is a legitimate setup — it just cannot be
*assumed*, which is why an unmatched configuration warns rather than guessing.

## Offsets and scale components

`detoffset`, `scalecomp` and `samoffset` come from the cycle's AgBe calibration,
determined at the start of the cycle by the instrument scientist. `scalecomp` is
the `detector1` array `[x, y, z]` where `y = scale_all × scale_y`.

Worked examples: 2026B `scalecomp = [1.004251, 1.057915, 1]`, `detoffset = 66.763`,
`samoffset = 285.0`. 2026A `[1.003571, 1.052902, 1]`, `detoffset = 77.244`.
Historical, from `202502_agbe/34965/banjo`: `scalecomp = [1.002, 1.0728155533894388, 1]`,
`detoffset = 84.38081`, `samoffset = 300` (banjo rack, ti-rack).

`samoffset` depends on the sample rack in use, so it is not purely a cycle
property — check it when the rack changes.

No AgBe calibration exists before cycle 2026A. Older data reduces without these
values rather than with invented ones (protocol CAL-05).
