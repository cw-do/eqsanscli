---
topic: absolute-scale
summary: Calibrating I(Q) to absolute intensity with a standard sample.
load: on-demand
updated: 2026-08-17
---

# Absolute scale

Reduced intensity is put on an absolute footing by comparing a **standard sample**
measured in the same configuration against a known reference profile.

## Procedure

1. Reduce the standard with `standardabsolutescale = 1.0`.
2. Compare the measured I(Q) against the reference over an overlap window,
   interpolating the measurement onto the reference's Q points and taking the mean
   ratio (`services/calibration_service.py`, default window 0.01 ≤ Q ≤ 0.1).
3. Apply the resulting factor as that configuration's `standardabsolutescale`.
4. Reduce the samples.

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
- Without a standard, output is on a **relative** scale. The preset's
  `standardabsolutescale` is then whatever was inherited — often from another
  experiment — so it must not be presented as absolute (protocol SCL-01).
- A factor far from recent values suggests a bad fit or the wrong reference
  (protocol SCL-03). Recent presets carry ≈0.19–0.23 for 4 m 10 Å; the acceptable
  range is **TBD**.
- The scale factor is a config parameter, so changing it marks reduced rows
  `modified` — they need re-reducing, which autopilot and `/reduce --new` handle.

## Interaction with stitching

The stitch target is the lowest-Q configuration because it carries the absolute
scale; other configurations are scaled onto it (protocol STC-03). If the
per-configuration absolute scales are right, the stitch scale factors come out
near 1 — a large one points at the calibration, background or transmission rather
than at the stitching (protocol STC-05).
