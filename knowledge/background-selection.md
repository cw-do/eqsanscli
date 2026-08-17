---
topic: background-selection
summary: What counts as a background, how it pairs with samples, and what gets no background.
load: on-demand
updated: 2026-08-17
---

# Background selection

The background is the sample environment measured **without** the sample: an
empty cell, an empty Ti cell, a banjo cell, an empty cup. Subtracting it removes
the container and environment scattering.

An **empty beam** is not a background — it is the direct beam, used for the beam
centre and for transmission normalisation (protocol EMP-03).

## Names seen in titles

Background: `bkg`, `background`, `banjo`, `emptycell`, `emptyticell`,
`empty ticell`, `ti-cell`, `ticell`. Empty beam: standalone `empty`, `emp`, `emt`,
or anything followed by `beam`.

Background keywords are tested first, so `emptyticell` classifies as background
even though it contains "empty" (protocol CAT-05). This matters because the two
roles are not interchangeable.

The keyword lists are a *starting guess from the title*. A sample legitimately
named `BkgG` is a sample, not a background — that is what `/reclass --sample BkgG
sample` is for, and it respects the `S-`/`T-` prefix so the scattering and
transmission runs land in the right classes.

## Pairing rules

- The background run comes from the **same configuration** as the row it serves
  (protocol BKG-01). `/assign bkg <sample>` does this by construction: it finds
  the named sample's `S-` and `T-` runs per configuration and sets both `bkg` and
  `bkgtrans`. A per-row `/set` can break it, so prefer `/assign bkg`.
- Set `bkgtrans` whenever `bkg` is set (protocol TBL-04). The background needs the
  same transmission treatment the sample got.
- One background sample per experiment unless there is a reason (protocol BKG-03).
- A row's background is never its own scattering run (protocol BKG-02).

## What gets no background

The background sample's own rows, and empty-beam rows, get **no** background
subtraction — their `bkg`/`bkgtrans` stay blank. Filling them with the empty-beam
run (an earlier behaviour) was wrong: it subtracted a calibration measurement
from a background measurement.

So a table where the banjo row has empty `Bkg`/`BkgTr` columns is **correct**, not
incomplete. This is the one case where the missing-background warning (TBL-03) is
expected.

## When there is no background at all

Some experiments deliberately measure none. Reduction proceeds — background is
advisory, not blocking — but the result includes container scattering, so it
should be stated rather than left implicit.

## Choosing between candidates

When several background candidates exist at a configuration, the deterministic
rules run out and judgement starts. Useful signals, strongest first:

1. The user named one (`--bkg banjo`, `/assign bkg emptyticell`) — that decides it.
2. The cell actually used for the samples in this experiment. The sample titles
   often name it.
3. Measured close in time to the samples, at the same configuration.
4. Adequate counting statistics — a very short background is noisy and will
   inject noise into every subtracted profile.

If two candidates are equally plausible, say so and ask; do not pick silently.
