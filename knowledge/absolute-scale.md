---
topic: absolute-scale
summary: Calibrating I(Q) to absolute intensity with a standard sample.
load: on-demand
updated: 2026-10-15
---

# Absolute scale

Reduced intensity is put on an absolute footing by comparing a **standard sample**
measured in the same configuration against a known reference profile.

## Procedure

1. Reduce the standard (at any scale s0 — 1.0 is customary).
2. Compare the measured I(Q) against the reference over an overlap window,
   interpolating the measurement onto the reference's Q points and taking the mean
   ratio f (`services/calibration_service.py`, default window **0.01 ≤ Q ≤ 0.03**;
   2.5 m / 2.5 Å curves start above it — use `--qmin 0.03 --qmax 0.1`).
3. Check the fit: the report gives the ratio's spread and f in the windows
   shifted by half a width either way; > 2 % means the curve does not follow the
   reference there — move the window rather than trust the number.
4. `--applynow` sets the configuration's scale to **s0 × f** (s0 read from the
   standard's `<name>.json`) and records where it came from. Before v0.48.0 it
   set f alone, which was wrong unless the standard had been reduced at 1.0.
5. Reduce the samples.

Each calibration is written to `calibration_<cfg>.json` and `.png` (reference vs
measured × f, window shaded) and appended to `calibration_history.jsonl` in the
output directory.

Autopilot does this as Steps 6–8. Manually it is `/reduce --sample porsil`, then
`/calibrate <file> --applynow` per configuration.

## The standard

Porsil (also spelled porasil) is the default, auto-detected by substring. Standard
names vary between cycles and users — `porsilb1`, `porsil b1`, `agb1` — so
`--standard <name>` overrides the detection.

References live in `absscale_reference/`: `NG3_B1_1413_4col.dat` (default) and
`NG7_ORNL_B1_All_4col.dat`.

## Rules

- Each configuration needs a standard measured **in that configuration** (protocol
  SCL-02). A factor from 4 m 10 Å does not apply to 2.5 m 2.5 Å.
- Without a standard, the scale is **1.0 and the data is relative (a.u.)**
  (protocol SCL-01). Presets no longer carry a scale — they held other
  experiments' factors, which were inherited silently (SCL-04).
- A factor you set yourself (`/set config <cfg> standardabsolutescale x`), even
  one borrowed from another experiment, is taken as correct and the data as
  absolute: that is your decision, and it is recorded as `user` (SCL-04).
- `/show config <cfg>` shows the scale with its origin and unit.
- A scale outside 0.01–50 is warned about (protocol SCL-03).
- The scale factor is a config parameter, so changing it marks reduced rows
  `modified` — they need re-reducing, which autopilot and `/reduce --new` handle.

## Interaction with stitching

The stitch target is the lowest-Q configuration because it carries the absolute
scale; other configurations are scaled onto it (protocol STC-03). If the
per-configuration absolute scales are right, the stitch scale factors come out
near 1 — a large one points at the calibration, background or transmission rather
than at the stitching (protocol STC-05).
