---
topic: troubleshooting
summary: Failure signatures seen in practice, their cause, and the fix.
load: on-demand
updated: 2026-08-17
---

# Troubleshooting

Signatures observed in real sessions. Add to this file when a new failure mode
costs someone time — that is what makes it worth keeping.

## Reduction refuses before starting

**"N of M selected row(s) cannot be reduced … no empty beam"**
The rows have no empty-beam run, which supplies the beam centre (protocol EMP-01).
Usually the empty-beam run exists but was classified as a transmission from its
title. Fix: `/reclass <run> empty` then `/matchruns`. If the table is already
reduced and you do not want a rebuild, `/set --config <id> emp <run>`.

**"Working table is empty"**
`/matchruns` has not run for this table. If you expected rows, check `/table list`
— they may be in another table.

## Reduction runs but a row fails

**Permission error on a mask or calibration file**
A path pointing into another IPTS's shared folder (protocol CAL-04). Presets used
to carry these. Fix: `/instrument apply` to re-resolve, or `/instrument check` to
list every unreadable file.

**File not found for flood / dark / flux**
The cycle folder changed or the preset is stale. `/instrument show` reports what
is resolved and from which cycle; `/instrument check` verifies existence.

**drtsans error with no obvious cause**
The per-row `.out` and `.err` files sit next to the reduction JSON in the output
directory, and the JSON itself records exactly what was passed. Check the JSON
first — a wrong path or a null where a value is required is visible there.

## Output looks wrong

**Intensity off by a constant factor**
Absolute scale. Either no standard was measured (output is relative, protocol
SCL-01) or the factor came from a different configuration (SCL-02). `/show config
<id>` shows `standardabsolutescale` and its source.

**A step or kink at a stitch overlap**
One configuration's background or transmission is off, or the overlap window sits
where a profile is unreliable. Inspect the per-configuration profiles before the
merged one (`stitching.md`).

**Container scattering still present**
No background, or a background from the wrong configuration (protocol BKG-01).
`/show table` — a blank `Bkg` column is expected only for the background sample
itself and for empty-beam rows (EMP-03).

**Noise injected across every profile**
A background with poor counting statistics propagates into everything subtracted
from it. Check the background run's duration.

## Table looks wrong

**A sample is missing from the table entirely**
Its runs are classified `ignore`, or its title matched a background/empty keyword
and it was grouped elsewhere. `/show catalog` shows the `Class` column;
`/reclass --sample <name> sample` restores a mis-keyworded sample, respecting the
`S-`/`T-` prefix.

**Rows appear at a configuration that does not exist**
Config IDs come from ONCat `detector_distance` / `wavelength`, so a run whose
title disagrees with its metadata lands where the metadata says (protocol CAT-06).
Trust the metadata.

**Runs spanning a cycle boundary**
`/matchruns` warns that a configuration's runs straddle two calibration cycles
(protocol TBL-07). All rows use the earlier cycle. Split the later runs into their
own table if they need the newer calibration.

## Calibration files not updating

**Still using last cycle's flood after a new cycle is published**
Values the user set with `/set config` are never overwritten automatically
(protocol CFG-03), so a hand-set path sticks. `/instrument show` marks these
"yours, kept"; `/instrument apply --force` overrides them.

**A new cycle's files are not being picked up at all**
The cycle folder needs at least one dark or flood run for its anchor run to exist.
`/instrument list` shows every cycle with its anchor run and what it holds.
