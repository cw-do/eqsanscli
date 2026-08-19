This is one experiment from raw runs to a stitched, absolutely-scaled I(Q). Each
step says what to expect and what to do when it reports a problem.

If the experiment is routine, [`/autopilot`](commands.html#cmd-autopilot) does all
of it in one command — read this anyway once, because it is the same sequence and
you will want to know which step failed when one does.

## 1 · Load the catalog

```
/load ipts 38681
```

Fetches every run in the experiment from ONCat with its title, detector distance,
wavelength, frequency, counts and duration, and classifies each one from its
title: scattering, transmission, background, empty beam.

```
/show catalog
```

Read the **Class** column. `S` scattering, `T` transmission, `BkgS`/`BkgT`
background, `EmpT` empty beam, `N` ignored. Classification is what everything
downstream pairs on, so fix it here rather than assigning runs by hand later:

```
/reclass 186517 empty          # this run is the empty beam
/reclass 186531,186532 scatt   # these are samples, whatever the title says
```

## 2 · Match the runs

```
/matchruns
```

Builds the working table: one row per scattering run, each paired with its
transmission, background, background transmission and empty beam **from its own
configuration**. In the same pass it applies the JSON preset for each
configuration and resolves the cycle's calibration files by run number.

Expect a summary like:

```
Matched 50 scattering runs across 2 configurations.
  Configurations: 4m10a, 2.5m2.5a
  Transmission matched: 48/50
  Background matched: 50/50
  Empty beam matched: 45/50
  Presets auto-applied: 4m10a, 2.5m2.5a
  Instrument files (machine physics): 2026B — sensitivity, dark, flux, offsets
```

Anything short of N/N needs attention before reducing. A row with no empty beam
cannot reduce at all — the empty beam supplies both the beam centre and the
transmission reference.

```
/set --config 4m10a emp 186517     # give a whole configuration its empty beam
/assign bkg emptyticell            # background by sample name, config-aware
/set 3 trans 186520                # one row, one field
/remove --sample test              # drop rows you do not want
```

## 3 · Check the table

```
/show table
```

Every row should have all five fields filled. Dashes mean unmatched. The `Status`
column starts as `ready`, becomes `done` after a successful reduction, and flips
to `modified` when you change something that invalidates the result — which is
how a re-run knows what to redo.

## 4 · Set the output directory

```
/set outputdir /SNS/EQSANS/IPTS-38681/shared/output/
```

Everything — reduced files, the merged I(Q), plots, `NOTE.md` — lands here.

## 5 · Calibrate the absolute scale

If the experiment measured a standard (usually porsil), reduce it first with a
scale of 1, then fit it against the reference:

```
/set config 4m10a standardabsolutescale 1.0
/reduce --sample porsil
/calibrate porsil_4m10a_Iq.dat --applynow
```

`--applynow` reads the configuration out of the filename, applies the fitted
factor to that configuration, and marks the affected rows for re-reduction. Repeat
per configuration: **a scale factor belongs to the configuration it was measured
in** and must not be borrowed from another.

With no standard in the experiment, the preset's `standardabsolutescale` is used
and the result is scaled but not independently verified.

## 6 · Reduce

```
/reduce all
```

Each row is reduced through drtsans, writing `{sample}_{config}_Iq.dat`,
the 2D `_Iqxqy.dat`, and the JSON that drove it. Failures are reported per row
with the reason; fix and re-run just those with `/reduce --new`.

## 7 · Stitch the configurations

```
/stitch smart
```

Groups each sample's configurations low-Q to high-Q, picks overlap windows —
preset ranges for known configuration pairs, computed ones otherwise — scales
each profile onto the target and writes `merged_{sample}_..._Iq.txt`. The report
shows the scale factor applied to each profile; a factor far from 1 means the
absolute scale or the overlap window deserves a look.

## 8 · Look at it

```
/plot merged_*.txt --save stitched.png --loglog
/list iq
```

Then hand it over:

```
/share merged_*.txt              # upload, get a 24-hour link
/zipnsend someone@ornl.gov       # zip and email
/confirm                         # record the experiment as reduced
```

## What to do when something looks wrong

| Symptom | Likely cause | Fix |
|---|---|---|
| Rows cannot reduce, "no empty beam" | the empty-beam run was never classified as one | `/reclass <run> empty` then `/matchruns` |
| Background from the wrong configuration | assigned per-row by hand | `/assign bkg <sample>` — it matches configuration for you |
| Absolute scale looks wrong by a constant | scale factor from another configuration | re-run `/calibrate` for that configuration |
| Stitched curves do not meet | overlap window or target | `/stitch smart`, or set the overlap by hand |
| Parameters look stale after a new cycle | session predates the calibration update | `/instrument apply` |

The [protocol](protocol.html) lists what a trustworthy reduction has to satisfy,
and which of those the tool checks for you.
